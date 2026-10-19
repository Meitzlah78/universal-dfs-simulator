import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest
import numpy as np,pandas as pd
from test_candidates import fixture


class WorkflowIntegrationTest(unittest.TestCase):
    def test_csv_ownership_survives_player_pool_loading(self):
        tree=ast.parse(Path('dfs_app.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='preserve_uploaded_ownership')
        ns={'np':np,'pd':pd};exec(compile(ast.Module(body=[fn],type_ignores=[]),'app','exec'),ns)
        players=pd.DataFrame({'Name':['A','B','C']},index=[4,7,9])
        raw=pd.DataFrame({'Own%':['35%','0%','bad'],'Field Own %':[99,99,99],
                          'MVP Ownership %':['12%',None,'200%']},index=players.index)
        result=ns['preserve_uploaded_ownership'](players,raw)
        self.assertEqual(result.loc[4,'Projected Ownership'],35)
        self.assertEqual(result.loc[7,'Projected Ownership'],0)
        self.assertTrue(pd.isna(result.loc[9,'Projected Ownership']))
        self.assertEqual(result.loc[4,'Projected MVP Ownership'],12)
        self.assertTrue(pd.isna(result.loc[9,'Projected MVP Ownership']))
        self.assertNotIn('Field Own %',result)

    def test_external_ownership_percent_strings_override_fallback(self):
        tree=ast.parse(Path('dfs_app.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='opponent_field_selection_weights')
        ns={'np':np,'pd':pd}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'app','exec'),ns)
        weights=ns['opponent_field_selection_weights'](
            pd.DataFrame({'Projected Ownership':['35%', ' 5% ', None, 'inf']}),
            np.array([1.,100.,50.,10.]))
        np.testing.assert_allclose(weights,[35.,5.,.01,.01])

    def test_candidate_helper_uses_separate_construction_and_evaluation(self):
        tree=ast.parse(Path('dfs_app.py').read_text())
        wanted={'FULL_ROSTER_STACK_OPTIONS','SECONDARY_STACK_OPTIONS','full_roster_stack_lookup','full_roster_stack_matches','build_joint_candidate_pool'}
        nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in wanted or isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in wanted for t in n.targets)]
        progress=SimpleNamespace(progress=Mock())
        state={'simulation_cap_hit_pct':{'original':1}}
        st=SimpleNamespace(session_state=state,info=Mock(),warning=Mock(),caption=Mock(),progress=lambda *a,**k:progress)
        pool,construction,roster=fixture()
        # A different matrix makes accidental construction/evaluation reuse visible.
        evaluation=construction*2+1
        simulate=Mock(side_effect=AssertionError("BUILD must not simulate"))
        loader=Mock(return_value=construction)
        ns={'np':np,'pd':pd,'st':st,'SIMULATION_COUNT':len(construction),'simulate_fd_play_by_play':simulate,'simulation_cache_root':lambda:Path('/unused')}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'dfs_app.py','exec'),ns)
        with patch('simmah_simulation_store.construction_for_build',loader):
            result=ns['build_joint_candidate_pool'](pool,'DraftKings','Classic',evaluation,roster,47000,50000)
        self.assertEqual(len(result),5000)
        from simmah_candidates import offense_vs_defense_allowed
        lookup=pool.set_index('Name').to_dict('index')
        slots=[slot for slot,_ in roster]
        self.assertTrue(all(offense_vs_defense_allowed(row,lookup) for row in result[slots].to_dict('records')))
        simulate.assert_not_called()
        self.assertEqual(loader.call_count,1)
        self.assertEqual(loader.call_args.kwargs["count"],len(construction))
        self.assertEqual(state['simulation_cap_hit_pct'],{'original':1})
        first=result.iloc[0];names=[first[s] for s,_ in roster]
        self.assertAlmostEqual(first['SimMean'],evaluation[names].sum(axis=1).mean(),places=3)
        self.assertTrue(state['candidate_engine_DraftKings_Classic']['independent_evaluation'])

    def test_all_format_paths_share_build_and_learning_adapters(self):
        source=Path('dfs_app.py').read_text()
        self.assertEqual(source.count('build_joint_candidate_pool(')-1,3)
        self.assertEqual(source.count('apply_learned_field(')-1,3)
        self.assertIn('"FanDuel", lineup_mode',source)
        self.assertIn('"DraftKings", "Classic"',source)
        self.assertIn('"DraftKings", "Showdown"',source)
        self.assertNotIn('_roi_sims = min(len(_sim_values), 500)',source)
        self.assertIn('for _, lineup in classic_export_portfolio.iterrows():',source)

    def test_classic_report_and_entries_share_assigned_portfolio(self):
        source=Path('dfs_app.py').read_text()
        self.assertNotIn('contest_entries = user_lineups.sort_values("Top1"',source)
        self.assertNotIn('st.dataframe(_saved_classic_entries',source)
        self.assertIn('data=classic_export_portfolio.to_csv(index=False).encode("utf-8")',source)
        self.assertIn('for _, lineup in classic_export_portfolio.iterrows():',source)
        self.assertIn("select_portfolio(classic_portfolio_source",source)

    def test_fanduel_joint_roi_reuses_selected_field_without_hidden_expansion(self):
        source=Path('dfs_app.py').read_text()
        tree=ast.parse(source)
        assignments=[n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_fd_final_field' for t in n.targets)]
        self.assertEqual(len(assignments),1)
        self.assertIsInstance(assignments[0].value,ast.Name)
        self.assertEqual(assignments[0].value.id,'opponent_df')
        self.assertNotIn('Building larger final ROI field',source)
        self.assertNotIn('_fd_extra_target',source)
        self.assertIn('compared = evaluate_contest(_fd_roi_sim, compared, _fd_final_field, fd_slots,',source)
        self.assertNotIn('_fd_holdout_pool',source)
        self.assertIn('fd_entry_file.getvalue(), fd_export_portfolio, fd_ids,',source)
        self.assertIn('fd_export_portfolio.to_csv(index=False)',source)

    def test_full_roster_contest_parameters_require_metadata_for_roi(self):
        tree=ast.parse(Path('dfs_app.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='full_roster_contest_parameters')
        ns={};exec(compile(ast.Module(body=[node],type_ignores=[]),'app','exec'),ns)
        resolve=ns['full_roster_contest_parameters']
        unknown=resolve({'your_entries':20},10000)
        self.assertFalse(unknown['payouts_known'])
        self.assertEqual(unknown['field_size'],10020)
        known=resolve({'field_size':100,'entry_fee':.25,'your_entries':20,'payouts':[(1,10,2)]},50)
        self.assertTrue(known['payouts_known'])
        self.assertEqual(known['field_size'],100)
        preset=resolve({'name':'45K Sun NFL Hail Mary','entry_fee':.25,'your_entries':20},10000)
        self.assertTrue(preset['payouts_known'])
        self.assertEqual(preset['field_size'],215568)

    @staticmethod
    def portfolio_fixture():
        from simmah_candidates import build_candidates
        pool,outcomes,roster=fixture()
        frame=build_candidates(pool,outcomes,roster,target=60,rng=np.random.default_rng(15))
        frame['Top1']=np.linspace(1,.1,len(frame))
        return pool,frame,[slot for slot,_ in roster]

    def test_fanduel_assigned_count_matches_owned_and_report_export_source(self):
        from simmah_portfolio_selection import select_portfolio
        tree=ast.parse(Path('dfs_app.py').read_text())
        nodes=[]
        for n in sorted((n for n in ast.walk(tree) if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name)),key=lambda n:n.lineno):
            name=n.targets[0].id
            if name=='_fd_owned_count':nodes.append(n)
            if name=='_fd_diverse_portfolio' and isinstance(n.value,ast.Call):nodes.append(n)
            if name=='fd_export_portfolio' and isinstance(n.value,ast.Call) and ast.unparse(n.value)=='_fd_diverse_portfolio.copy()':nodes.append(n)
        pool,frame,slots=self.portfolio_fixture()
        for shown in [3,100]:
            ns={'np':np,'pd':pd,'select_portfolio':select_portfolio,'fd_all_ranked':frame,
                'fd_slots':slots,'fd_rank_column':'Top1','fd_rank_count':shown,
                'fd_player_display':pool,'st':SimpleNamespace(session_state={'selected_fd_contest':{'your_entries':20}}),
                'full_roster_contest_parameters':lambda *args:{'owned':20}}
            exec(compile(ast.Module(body=nodes,type_ignores=[]),'app','exec'),ns)
            assigned=ns['fd_export_portfolio']
            self.assertEqual(len(assigned),20)
            self.assertEqual(assigned[slots].apply(lambda row:tuple(sorted(row)),axis=1).nunique(),20)

    def test_classic_assignment_matches_owned_entries_not_display_count(self):
        from simmah_portfolio_selection import select_portfolio
        tree=ast.parse(Path('dfs_app.py').read_text())
        wanted={'_classic_assignment_count','_classic_slots','classic_export_portfolio','_classic_unique_entries'}
        nodes=sorted((n for n in ast.walk(tree) if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in wanted),key=lambda n:n.lineno)
        first=[];seen=set()
        for node in nodes:
            name=node.targets[0].id
            if name=='_classic_slots' and 'classic_portfolio_source' not in ast.unparse(node.value):continue
            if name not in seen:first.append(node);seen.add(name)
        pool,frame,slots=self.portfolio_fixture()
        for displayed,owned in [(3,20),(100,20)]:
            ns={'np':np,'select_portfolio':select_portfolio,
                'st':SimpleNamespace(session_state={'selected_dk_contest':{'your_entries':owned}}),
                'classic_entry_count':owned,'classic_top_portfolio':frame.head(displayed),
                'classic_portfolio_source':frame,'classic_rank_metric':'Top1','control_map':{}}
            exec(compile(ast.Module(body=first,type_ignores=[]),'dfs_app.py','exec'),ns)
            assigned=ns['classic_export_portfolio']
            self.assertEqual(len(assigned),owned)
            self.assertEqual(assigned[slots].apply(lambda row:tuple(sorted(row)),axis=1).nunique(),owned)


if __name__=='__main__':unittest.main()
