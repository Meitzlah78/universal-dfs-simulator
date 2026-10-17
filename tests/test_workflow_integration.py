import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
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
        simulate=Mock(return_value=construction)
        ns={'np':np,'pd':pd,'st':st,'SIMULATION_COUNT':len(construction),'simulate_fd_play_by_play':simulate}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'dfs_app.py','exec'),ns)
        result=ns['build_joint_candidate_pool'](pool,'DraftKings','Classic',evaluation,roster,47000,50000)
        self.assertEqual(len(result),5000)
        self.assertEqual(simulate.call_count,1)
        self.assertEqual(simulate.call_args.args[2],len(construction))
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
        self.assertIn('.sort_values(classic_rank_metric, ascending=False, kind="stable")',source)

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
        self.assertIn('lineup = fd_export_portfolio.iloc[entry_number]',source)
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

    def test_fanduel_assigned_count_matches_owned_and_report_export_source(self):
        tree=ast.parse(Path('dfs_app.py').read_text())
        assignments=sorted((n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in {'_fd_entry_seed','fd_export_portfolio'} for t in n.targets)),key=lambda n:n.lineno)
        nodes=[n for n in assignments if n.targets[0].id=='_fd_entry_seed' or isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Attribute) and n.value.func.attr=='reset_index' and '_fd_entry_seed' in ast.unparse(n.value)]
        for shown in [3,100]:
            frame=pd.DataFrame({'QB':[f'p{i}' for i in range(shown)]})
            ns={'pd':pd,'np':np,'fd_results':frame,'_fd_spec':{'owned':20}}
            exec(compile(ast.Module(body=nodes,type_ignores=[]),'app','exec'),ns)
            assigned=ns['fd_export_portfolio']
            self.assertEqual(len(assigned),20)
            self.assertEqual(assigned.QB.nunique(),min(shown,20))

    def test_classic_assignment_matches_owned_entries_not_display_count(self):
        tree=ast.parse(Path('dfs_app.py').read_text())
        wanted={'_classic_assignment_count','_classic_unique_entries','classic_export_portfolio'}
        nodes=sorted((n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in wanted for t in n.targets)),key=lambda n:n.lineno)
        first=[];seen=set()
        for node in nodes:
            name=node.targets[0].id
            if name not in seen:first.append(node);seen.add(name)
        for displayed,owned in [(3,20),(100,20)]:
            frame=pd.DataFrame({'QB':[f'p{i}' for i in range(displayed)]})
            ns={'np':np,'st':SimpleNamespace(session_state={'selected_dk_contest':{'your_entries':owned}}),
                'classic_entry_count':owned,'classic_top_portfolio':frame}
            exec(compile(ast.Module(body=first,type_ignores=[]),'dfs_app.py','exec'),ns)
            assigned=ns['classic_export_portfolio']
            self.assertEqual(len(assigned),owned)
            self.assertLessEqual(assigned['QB'].nunique(),min(displayed,owned))
            self.assertTrue(set(assigned['QB']).issubset(set(frame.head(owned)['QB'])))


if __name__=='__main__':unittest.main()
