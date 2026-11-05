import io,json,unittest,zipfile
from unittest.mock import patch
import numpy as np
import pandas as pd
from simmah_nba_swap_portfolio import select_swap_portfolio,audit_swap_portfolio

class SwapPortfolioTests(unittest.TestCase):
    def fixture(self):
        pool=pd.DataFrame({'Player ID':[str(i) for i in range(8)],'Name':['Player '+str(i) for i in range(8)],
            'Projection':[30.]*8,'Injury Status':['Active']*8,'Position':['PG']*8})
        locked=np.array([True,True,False,False,False,False,False,False])
        originals=np.array([[0,3],[0,4],[1,5],[1,6]])
        candidates=np.array([[0,2],[0,3],[0,4],[1,2],[1,5],[1,6]])
        return pool,locked,originals,candidates,{0:np.arange(3),1:np.arange(3,6)},{0:[0,1],1:[2,3]}

    def test_joint_caps_group_quotas_and_recorded_assignment(self):
        p,l,o,c,g,e=self.fixture()
        selected,meta=select_swap_portfolio(p,o,l,c,g,e,[10,9,8,10,9,8],diversity=0)
        self.assertEqual(len(selected),4)
        self.assertEqual(set(selected[:2])&set(range(3)),set(selected[:2]))
        self.assertTrue((c[selected[:2],0]==0).all());self.assertTrue((c[selected[2:],0]==1).all())
        self.assertLessEqual((c[selected]==2).sum(),2)
        self.assertEqual(len(set(tuple(sorted(r)) for r in c[selected])),4)
        self.assertFalse(meta['locked_overages'])

    def test_fade_minimum_and_infeasible_caps_never_relax(self):
        p,l,o,c,g,e=self.fixture()
        controls={'2':{'Fade':True},'3':{'Min Exposure %':25}}
        selected,_=select_swap_portfolio(p,o,l,c,g,e,[10,9,8,10,9,8],controls=controls)
        self.assertNotIn(2,c[selected]);self.assertIn(3,c[selected])
        with self.assertRaisesRegex(ValueError,'No full portfolio'):
            select_swap_portfolio(p,o,l,c,g,e,[10,9,8,10,9,8],controls={'2':{'Fade':True},'3':{'Fade':True}})

    def test_locked_overages_are_explicit_and_only_inherited(self):
        p,l,o,c,g,e=self.fixture()
        o=np.array([[0,3],[0,4],[0,5],[1,6]])
        c=np.array([[0,2],[0,3],[0,4],[0,5],[1,2],[1,6]])
        selected,meta=select_swap_portfolio(p,o,l,c,{0:np.arange(4),1:np.arange(4,6)},
            {0:[0,1,2],1:[3]},np.arange(6),diversity=0)
        self.assertEqual(meta['locked_overages'][0]['Locked entries'],3)
        self.assertEqual((c[selected]==0).sum(),3)
        mutated=c[selected].copy();mutated[:,1]=2
        with self.assertRaisesRegex(ValueError,'Player 2'):
            audit_swap_portfolio(p,o,mutated,l)

    def test_normalized_diversity_does_not_depend_on_metric_units(self):
        p,l,o,c,g,e=self.fixture();metric=np.array([10,9,8,10,9,8.])
        a,_=select_swap_portfolio(p,o,l,c,g,e,metric,diversity=50)
        b,_=select_swap_portfolio(p,o,l,c,g,e,metric*100+3,diversity=50)
        np.testing.assert_array_equal(a,b)

    def test_fully_locked_duplicate_entries_preserved_only_at_existing_count(self):
        p,l,o,c,g,e=self.fixture();l[:]=True
        o=np.array([[0,3],[0,3],[1,4],[1,5]])
        selected,_=select_swap_portfolio(p,o,l,o,{0:np.array([0,1]),1:np.array([2]),2:np.array([3])},
            {0:[0,1],1:[2],2:[3]},[0,0,0,0])
        self.assertEqual(len(selected),4)
        np.testing.assert_array_equal(o[selected],o)

    def test_export_rechecks_manual_fade_even_if_lineup_unchanged(self):
        from test_nba_late_swap import LateSwapTests
        from simmah_nba_late_swap import export_swaps
        f=LateSwapTests();f.setUp()
        result={'original_entries':[f.rows[1][:13]],'lineups':[f.ids],
            'controls':{f.ids[1]:{'Fade':True}}}
        with patch('simmah_nba_late_swap.entry_rows',return_value=result['original_entries']):
            with self.assertRaisesRegex(ValueError,'exposure check failed'):
                export_swaps(f.template,'42-99',f.pool,result,now=f.now)

    def test_both_sites_selection_archive_roundtrips_candidate_ids_scores_and_locks(self):
        from simmah_nba_swap_archive import make_swap_package
        from simmah_slate_workspaces import decode
        from hashlib import sha256
        for site in ['DraftKings','FanDuel']:
            p,l,o,c,g,e=self.fixture();p.attrs['platform']=site
            from simmah_nba_rules import rules_for
            size=len(rules_for(p)['slots'])
            rows=[[str(i) for i in range(size)]]
            result={'candidate_player_ids':rows,'candidate_report':pd.DataFrame({'Top 1%':[1.5]}),
                'lineups':rows,'locked_at_selection':l.tolist(),'inputs_snapshot':p,
                'selected_candidate_indices':[0],'selection':{'version':'test'},
                'controls':{'2':{'Fade':True}}}
            _,raw,manifest=make_swap_package(p,'42',result)
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                for name,meta in manifest['files'].items():
                    self.assertEqual(sha256(z.read(name)).hexdigest(),meta['sha256'])
                restored=decode(json.loads(z.read('late_swap.json')))
            self.assertEqual(restored['candidate_player_ids'],rows)
            self.assertEqual(restored['candidate_report'].iloc[0]['Top 1%'],1.5)
            self.assertEqual(restored['controls'],result['controls'])
            self.assertEqual(restored['locked_at_selection'],l.tolist())
            self.assertEqual(restored['inputs_snapshot'].attrs['platform'],site)

    def test_simulated_selection_and_archive_on_both_site_roster_sizes(self):
        from test_nba_candidates import CandidateTests
        from simmah_nba_candidates import build_candidates
        from simmah_nba_sim_late_swap import simulate_swap_entries
        from simmah_nba_rules import rules_for
        for site in ['DraftKings','FanDuel']:
            p,outcomes=CandidateTests().fixture();p.attrs['platform']=site
            p['Name']=p['Player ID'];p['Opponent']='X'
            p['Game Start']='2026-11-04T21:00:00-05:00'
            initial=build_candidates(p,outcomes,target=10)['indices']
            entries=[[str(i),'42','Contest','.25',*p.iloc[row]['Player ID'].tolist()] for i,row in enumerate(initial[:4])]
            def factory(n,seed,ids):return np.random.default_rng(seed).gamma(4,8,(n,len(p)))
            with patch('simmah_nba_sim_late_swap.entry_rows',return_value=entries):
                result=simulate_swap_entries(b'', '42',p,factory,
                    {'indices':initial,'copies':np.ones(10,int)},[1,0,0,0,0,0,0,0,0,0,0],.25,
                    now=pd.Timestamp('2026-11-04T23:00:00Z'),simulations=20,candidate_target=100,pregame_locked=True)
            self.assertEqual(len(result['lineups']),4)
            self.assertEqual(len(result['lineups'][0]),len(rules_for(p)['slots']))
            counts=pd.Series(np.array(result['lineups']).ravel()).value_counts()
            self.assertLessEqual(counts.max(),2)
            for number,index in enumerate(result['selected_candidate_indices']):
                self.assertEqual(result['lineups'][number],result['candidate_player_ids'][index])

    def test_tipoff_reconciliation_clears_replaced_candidate_reference(self):
        from test_nba_late_swap import LateSwapTests
        from simmah_nba_late_swap import revalidate_current_locks
        f=LateSwapTests();f.setUp();changed=list(f.ids);changed[1]=f.pool.iloc[9]['Player ID']
        result={'lineups':[changed],'original_entries':[f.rows[1][:13]],
            'selected_candidate_indices':[7],
            'report':pd.DataFrame({'Candidate index':[7],'Status':['Sim-selected'],'Changes':[1]})}
        current=revalidate_current_locks(f.pool,result,now=f.now+pd.Timedelta(hours=3))
        self.assertEqual(current['lineups'][0],f.ids)
        self.assertIsNone(current['selected_candidate_indices'][0])
        self.assertTrue(pd.isna(current['report'].iloc[0]['Candidate index']))
        self.assertEqual(result['selected_candidate_indices'],[7])

if __name__=='__main__':unittest.main()
