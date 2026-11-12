import io,unittest
import numpy as np,pandas as pd
from simmah_fantasylabs_ownership import apply_snapshot,full_preferences,role_preferences,field_report,invalidate_field,CPT,FLEX

class FantasyLabsTests(unittest.TestCase):
    def fixture(self):
        pool=pd.DataFrame({'Name':['Player '+str(i) for i in range(10)],'Team':['JAX','BAL']*5,
            'Position':['WR']*10,'Salary':[7000]*10,'Projection':[20.]*10,
            'Game Info':['JAX@BAL 11/05/2026 08:15PM ET']*10})
        rows=[]
        for i in range(10):
            for role,own in [('CPT',10.),('FLEX',50.)]:
                rows.append({'Source':'FantasyLabs SimLabs','Source URL':'https://www.fantasylabs.com/nfl/simlabs/',
                    'Captured UTC':'2026-11-05T19:27:47Z','Source update label':'Latest Sims update: 11/04/2026 8:34PM EST',
                    'Site':'DraftKings','Slate date':'2026-11-05','Matchup':'JAX @ BAL',
                    'Team':pool.iloc[i].Team,'Role':role,'Player':pool.iloc[i].Name,
                    'Projected Ownership %':own,'Optimal %':own})
        return pool,pd.DataFrame(rows)
    def apply(self,p,f):return apply_snapshot(p,f.to_csv(index=False).encode())
    def test_separate_roles_optimal_never_becomes_input_or_cap(self):
        p,f=self.fixture();before=p.copy();f.loc[f.Role=='CPT','Optimal %']=1
        result,meta=self.apply(p,f)
        fw,cw=role_preferences(result)
        np.testing.assert_array_equal(fw,[50]*10);np.testing.assert_array_equal(cw,[10]*10)
        pd.testing.assert_frame_equal(p,before)
        np.testing.assert_array_equal(result.Projection,p.Projection)
        self.assertNotIn('Max Exposure %',result)
        self.assertEqual(meta['matched_players'],10)
        self.assertIsNone(meta['ownership_updated_utc'])
    def test_dk_import_matches_out_salary_players_before_injury_exclusion(self):
        import ast
        from pathlib import Path
        p,f=self.fixture()
        p.loc[0,'Name']='Cam Skattebo'
        f.loc[f.Player=='Player 0','Player']='Cam Skattebo'
        p['Injury Status']='Active';p.loc[0,'Injury Status']='Out'
        # Reproduce the old failure, then check the full-slate import retains shares.
        with self.assertRaisesRegex(ValueError,'Cam Skattebo'):
            self.apply(p.iloc[1:].reset_index(drop=True),f)
        result,meta=self.apply(p,f)
        eligible=result[result['Injury Status']!='Out'].reset_index(drop=True)
        self.assertNotIn('Cam Skattebo',eligible.Name.tolist())
        fw,cw=role_preferences(eligible)
        np.testing.assert_array_equal(fw,[50]*9)
        np.testing.assert_array_equal(cw,[10]*9)
        self.assertEqual(meta['raw_totals'],{'CPT':100.,'FLEX':500.})
        tree=ast.parse(Path('dfs_app.py').read_text())
        calls={}
        for node in ast.walk(tree):
            if (isinstance(node,ast.Call) and isinstance(node.func,ast.Name)
                    and node.func.id in {'render_snapshot','apply_injury_statuses'}
                    and any(isinstance(arg,ast.Name) and arg.id=='players_df' for arg in node.args)):
                calls[node.func.id]=node.lineno
        self.assertLess(calls['render_snapshot'],calls['apply_injury_statuses'])

    def test_wrong_site_slate_teams_and_duplicates_block(self):
        p,f=self.fixture()
        for col,value in [('Site','FanDuel'),('Slate date','2026-11-06'),('Team','NYJ')]:
            bad=f.copy();bad.loc[0,col]=value
            with self.assertRaises(ValueError):self.apply(p,bad)
        with self.assertRaisesRegex(ValueError,'Duplicate'):self.apply(p,pd.concat([f,f.iloc[:1]]))
    def test_incomplete_and_invalid_numbers_block(self):
        p,f=self.fixture()
        with self.assertRaisesRegex(ValueError,'coverage'):self.apply(p,f.iloc[1:])
        for value in ['',float('nan'),-1,101]:
            bad=f.copy();bad['Projected Ownership %']=bad['Projected Ownership %'].astype(object);bad.loc[0,'Projected Ownership %']=value
            with self.assertRaises(ValueError):self.apply(p,bad)
        bad=f.copy();bad.loc[0,'Projected Ownership %']=9
        with self.assertRaisesRegex(ValueError,'totals'):self.apply(p,bad)
    def test_exact_team_name_alias_and_defense_match(self):
        p,f=self.fixture();p.loc[0,'Name']='Brian Thomas Jr.';f.loc[f.Player=='Player 0','Player']='Brian Thomas'
        p.loc[1,['Name','Position']]=['Baltimore Ravens','DST'];f.loc[f.Player=='Player 1','Player']='Baltimore Defense'
        p.loc[2,'Name']='Matt Hibner';f.loc[f.Player=='Player 2','Player']='Matthew Hibner'
        result,_=self.apply(p,f);self.assertTrue(result[CPT].notna().all())
        bad=f.copy();bad.loc[0,'Player']='Unrelated Player'
        with self.assertRaisesRegex(ValueError,'not uniquely matched'):self.apply(p,bad)
    def test_greg_desrosiers_matches_draftkings_gregory_in_both_roles(self):
        p,f=self.fixture()
        p.loc[0,'Name']='Gregory Desrosiers'
        f.loc[f.Player=='Player 0','Player']='Greg Desrosiers'
        result,meta=self.apply(p,f)
        self.assertEqual(result.loc[0,CPT],10.)
        self.assertEqual(result.loc[0,FLEX],50.)
        self.assertEqual(meta['matched_players'],10)
        # An alias still requires the same team and an unambiguous salary identity.
        bad=f.copy();bad.loc[bad.Player=='Greg Desrosiers','Team']='BAL'
        with self.assertRaisesRegex(ValueError,'Greg Desrosiers'):self.apply(p,bad)
        duplicate=p.iloc[:1].copy();duplicate['Name']='Greg Desrosiers'
        with self.assertRaisesRegex(ValueError,'Ambiguous'):
            self.apply(pd.concat([p,duplicate],ignore_index=True),f)

    def test_authorized_fidone_exclusion_is_scoped_to_tonights_dk_slate(self):
        from simmah_fantasylabs_ownership import apply_authorized_slate_exclusions
        p,f=self.fixture();p['Team']=p.Team.replace({'JAX':'WAS','BAL':'NYG'})
        p['Game Info']='WAS@NYG 11/12/2026 08:15PM ET'
        p.loc[1,'Name']='Thomas Fidone II'
        p['Projected CPT Own %']=10.;p['Projected Flex Ownership']=50.
        p.loc[1,['Projected CPT Own %','Projected Flex Ownership']]=np.nan
        before=p.copy(deep=True)
        result=apply_authorized_slate_exclusions(p)
        self.assertNotIn('Thomas Fidone II',result.Name.tolist())
        self.assertEqual(len(result),9)
        self.assertIn('authorized_slate_exclusions',result.attrs)
        role_preferences(result)
        pd.testing.assert_frame_equal(p,before)
        for site,mode in [('FanDuel','single_game'),('DraftKings','full_roster')]:
            self.assertEqual(len(apply_authorized_slate_exclusions(p,site,mode)),10)
        other=p.copy();other['Game Info']='WAS@NYG 11/19/2026 08:15PM ET'
        self.assertEqual(len(apply_authorized_slate_exclusions(other)),10)
        other=p.copy();other['Team']=other.Team.replace({'WAS':'DAL'})
        self.assertEqual(len(apply_authorized_slate_exclusions(other)),10)

    def test_all_unmatched_players_and_roles_are_reported_together(self):
        p,f=self.fixture()
        f.loc[f.Player=='Player 0','Player']='Missing One'
        f.loc[f.Player=='Player 1','Player']='Missing Two'
        with self.assertRaises(ValueError) as caught:self.apply(p,f)
        message=str(caught.exception)
        for name in ['Missing One','Missing Two']:
            self.assertIn(name,message)
        self.assertIn('CPT',message);self.assertIn('FLEX',message)

    def test_missing_unprojected_salary_rows_remain_unknown_and_no_eligible_fallback(self):
        p,f=self.fixture();extra=p.iloc[:1].copy();extra['Name']='Unknown reserve';extra['Projection']=0
        p=pd.concat([p,extra],ignore_index=True)
        result,_=self.apply(p,f);self.assertTrue(pd.isna(result[CPT].iloc[-1]))
        with self.assertRaisesRegex(ValueError,'missing'):role_preferences(result)
        self.assertEqual(role_preferences(result.iloc[:-1])[0].sum(),500)

    def test_fd_missing_coverage_reports_exact_players_and_roles(self):
        pool=pd.DataFrame({'Name':['Missing receiver','Missing kicker','Covered'],
            'Team':['WAS','NYG','WAS'],FLEX:[np.nan,20.,30.],
            'Projected MVP Ownership':[5.,np.nan,0.]})
        pool.attrs['fantasylabs_ownership']={'site':'FanDuel'}
        before=pool.copy(deep=True)
        with self.assertRaises(ValueError) as caught:role_preferences(pool)
        message=str(caught.exception)
        self.assertIn('Missing receiver (WAS, FLEX)',message)
        self.assertIn('Missing kicker (NYG, MVP)',message)
        self.assertNotIn('Covered',message)
        pd.testing.assert_frame_equal(pool,before)

    def test_fd_absent_role_column_reports_players_instead_of_keyerror(self):
        pool=pd.DataFrame({'Name':['Player'], 'Team':['WAS'], FLEX:[20.]})
        pool.attrs['fantasylabs_ownership']={'site':'FanDuel'}
        with self.assertRaisesRegex(ValueError,r'Player \(WAS, MVP\)'):role_preferences(pool)
    def test_removing_or_changing_source_invalidates_only_downstream_outputs(self):
        state={'simulation_df':'sim','candidates_df':'candidates','contest_field_df':'old','portfolio_df':'old portfolio'}
        self.assertTrue(invalidate_field(state,('slate',),'first'))
        self.assertEqual(state['simulation_df'],'sim');self.assertEqual(state['candidates_df'],'candidates')
        self.assertEqual(state['fantasylabs_ownership_previous_outputs']['portfolio_df'],'old portfolio')
        state['contest_field_df']='new'
        self.assertFalse(invalidate_field(state,('slate',),'first'));self.assertEqual(state['contest_field_df'],'new')
        self.assertTrue(invalidate_field(state,('slate',),None));self.assertNotIn('contest_field_df',state)
    def test_report_measures_actual_role_counts(self):
        p,f=self.fixture();result,_=self.apply(p,f)
        field=pd.DataFrame([{'Captain':'Player 0',**{'Flex'+str(i):'Player '+str(i) for i in range(1,6)}}])
        report=field_report(field,result).set_index('Name')
        self.assertEqual(report.loc['Player 0','Field CPT %'],100)
        self.assertEqual(report.loc['Player 1','Field FLEX %'],100)

    def test_fanduel_mvp_and_anyflex_are_independent(self):
        p,f=self.fixture();f['Site']='FanDuel';f['Role']=f.Role.replace({'CPT':'MVP','FLEX':'AnyFLEX'})
        p['Team']=p.Team.replace({'JAX':'JAC'})
        result,meta=apply_snapshot(p,f.to_csv(index=False).encode(),site='FanDuel')
        fw,cw=role_preferences(result)
        np.testing.assert_array_equal(fw,[50]*10);np.testing.assert_array_equal(cw,[10]*10)
        self.assertEqual(meta['special_role'],'MVP');self.assertNotIn(CPT,result)
        field=pd.DataFrame([{'MVP':'Player 0',**{'FLEX'+str(i):'Player '+str(i) for i in range(1,6)}}])
        self.assertEqual(field_report(field,result).iloc[0]['Field MVP %'],100)
        with self.assertRaises(ValueError):apply_snapshot(p,f.to_csv(index=False).encode(),site='DraftKings')
    def test_both_full_roster_sites_preserve_approximate_totals(self):
        for site in ['DraftKings','FanDuel']:
            p,f=self.fixture();f=f[f.Role=='FLEX'].copy();f['Site']=site;f['Role']='WR'
            f['Projected Ownership %']=89.5;f['Optimal %']=90;f['Slate date']=''
            raw=f.to_csv(index=False).encode()
            with self.assertRaisesRegex(ValueError,'unconfirmed'):apply_snapshot(p,raw,site,'full_roster')
            result,meta=apply_snapshot(p,raw,site,'full_roster',confirmed_undated=True)
            self.assertEqual(meta['raw_totals']['overall'],895)
            np.testing.assert_array_equal(full_preferences(result),[89.5]*10)
            np.testing.assert_array_equal(result.Projection,p.Projection)
            self.assertNotIn(CPT,result);self.assertNotIn(FLEX,result)
    def test_full_roster_rejects_role_snapshot_or_missing_eligible_data(self):
        p,f=self.fixture()
        with self.assertRaisesRegex(ValueError,'position'):apply_snapshot(p,f.to_csv(index=False).encode(),mode='full_roster')
        p['Projected Ownership']=[float('nan')]+[90]*9
        with self.assertRaisesRegex(ValueError,'missing'):full_preferences(p)
    def test_classic_and_fanduel_caches_cannot_reuse_old_comparisons(self):
        classic={'classic_lineups':'candidates','classic_contest_comparison_df':'old','classic_contest_field_df':'old'}
        invalidate_field(classic,('slate',),'new',mode='full_roster')
        self.assertEqual(classic['classic_lineups'],'candidates');self.assertNotIn('classic_contest_comparison_df',classic)
        for mode in ['single_game','full_roster']:
            state={'fd_saved_builds':{('slate',):{'lineups':'old'}},'fd_contest_comparison_'+mode:'old',
                   'fd_lineups_'+mode:'old','fd_simulation_df_'+mode:'sim'}
            invalidate_field(state,('slate',),'new',site='FanDuel',mode=mode)
            self.assertNotIn('fd_contest_comparison_'+mode,state);self.assertNotIn('fd_lineups_'+mode,state)
            self.assertEqual(state['fd_simulation_df_'+mode],'sim');self.assertNotIn(('slate',),state['fd_saved_builds'])

    def test_draftdashboard_all_four_nfl_formats(self):
        for site in ['DraftKings','FanDuel']:
            for mode in ['single_game','full_roster']:
                with self.subTest(site=site,mode=mode):
                    p,f=self.fixture()
                    f['Source']='DraftDashboard';f['Site']=site;f['Sport']='NFL'
                    f=f.drop(columns=['Optimal %','Source URL','Matchup'])
                    if site=='FanDuel':f['Role']=f.Role.replace({'CPT':'MVP','FLEX':'AnyFLEX'})
                    if mode=='full_roster':
                        f=f[f.Role.isin(['FLEX','AnyFLEX'])].copy()
                        f['Role']='WR';f['Projected Ownership %']=90.
                    f=f.rename(columns={'Slate date':'Slate Date','Role':'Position','Source update label':'Source Update ET'})
                    f['Projected Ownership %']=f['Projected Ownership %'].astype(str)+'%'
                    result,meta=apply_snapshot(p,f.to_csv(index=False).encode(),site,mode)
                    self.assertEqual(meta['source'],'DraftDashboard')
                    self.assertTrue(result['Ownership Source'].str.startswith('DraftDashboard').all())
                    self.assertFalse(any('Optimal %' in c for c in result))
                    np.testing.assert_array_equal(result.Projection,p.Projection)
                    if mode=='full_roster':np.testing.assert_array_equal(full_preferences(result),[90]*10)
                    else:
                        fw,cw=role_preferences(result)
                        np.testing.assert_array_equal(fw,[50]*10)
                        np.testing.assert_array_equal(cw,[10]*10)

    def test_dashboard_rejects_wrong_sport_mixed_sources_and_missing_roles(self):
        p,f=self.fixture();f['Source']='DraftDashboard';f=f.drop(columns=['Optimal %'])
        bad=f.copy();bad['Sport']='NBA'
        with self.assertRaisesRegex(ValueError,'NFL'):self.apply(p,bad)
        bad=f.copy();bad.loc[0,'Source']='FantasyLabs SimLabs'
        with self.assertRaises(ValueError):self.apply(p,bad)
        with self.assertRaisesRegex(ValueError,'Both special-role'):self.apply(p,f[f.Role=='FLEX'])

    def test_dashboard_clears_old_optimal_data_and_changes_identity(self):
        p,f=self.fixture();old,old_meta=self.apply(p,f)
        f['Source']='DraftDashboard';f=f.drop(columns=['Optimal %'])
        result,meta=self.apply(old,f)
        self.assertFalse(any('Optimal %' in c for c in result))
        self.assertNotEqual(meta['sha256'],old_meta['sha256'])
        state={}
        invalidate_field(state,('slate',),old_meta['sha256'])
        state['portfolio_df']='old'
        self.assertTrue(invalidate_field(state,('slate',),meta['sha256']))
        self.assertNotIn('portfolio_df',state)

    def test_live_opponent_weights_prefer_import_over_old_selection_columns(self):
        import ast,types
        from pathlib import Path
        from unittest.mock import patch
        tree=ast.parse(Path('dfs_app.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='opponent_field_selection_weights')
        namespace={'np':np,'pd':pd}
        fake=types.ModuleType('simmah_game_lines');fake.field_market_factors=lambda pool,markets:np.ones(len(pool))
        with patch.dict('sys.modules',{'simmah_game_lines':fake}):
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'<live field weights>','exec'),namespace)
            p,f=self.fixture();result,_=self.apply(p,f)
            result['Ownership Selection Weight']=1.;result['Projected Own %']=2.
            weights=namespace['opponent_field_selection_weights'](result,np.ones(len(result)))
        np.testing.assert_array_equal(weights,[60]*10)

if __name__=='__main__':unittest.main()


