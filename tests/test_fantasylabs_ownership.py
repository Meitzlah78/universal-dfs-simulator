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
    def test_missing_unprojected_salary_rows_remain_unknown_and_no_eligible_fallback(self):
        p,f=self.fixture();extra=p.iloc[:1].copy();extra['Name']='Unknown reserve';extra['Projection']=0
        p=pd.concat([p,extra],ignore_index=True)
        result,_=self.apply(p,f);self.assertTrue(pd.isna(result[CPT].iloc[-1]))
        with self.assertRaisesRegex(ValueError,'missing'):role_preferences(result)
        self.assertEqual(role_preferences(result.iloc[:-1])[0].sum(),500)
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

if __name__=='__main__':unittest.main()

