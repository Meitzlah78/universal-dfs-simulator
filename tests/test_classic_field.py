import unittest
import numpy as np
from simmah_classic_field import classic_tournament_mask


class ClassicFieldTest(unittest.TestCase):
    def test_running_back_does_not_satisfy_qb_pass_catcher_stack(self):
        positions=np.array(['QB','RB','RB','WR','WR','WR','TE','TE','DST'])
        teams=np.array(['A','A','B','C','D','E','F','G','H'])
        picks=np.arange(9)[None,:]
        self.assertFalse(classic_tournament_mask(picks,teams,positions)[0])
        for slot in [3,6,7]:
            changed=teams.copy();changed[slot]='A'
            self.assertTrue(classic_tournament_mask(picks,changed,positions)[0])

    def test_duplicate_players_and_nine_same_team_are_rejected(self):
        positions=['QB','RB','RB','WR','WR','WR','TE','TE','DST']
        picks=np.arange(9)[None,:]
        self.assertFalse(classic_tournament_mask(picks,['A']*9,positions)[0])
        duplicate=picks.copy();duplicate[0,2]=duplicate[0,1]
        self.assertFalse(classic_tournament_mask(duplicate,['A']*8+['B'],positions)[0])
        self.assertTrue(classic_tournament_mask(picks,['A']*8+['B'],positions)[0])

    def test_fanduel_four_player_team_limit(self):
        positions=['QB','RB','RB','WR','WR','WR','TE','TE','D']
        picks=np.arange(9)[None,:]
        teams=['A','A','B','A','A','C','A','D','E']
        self.assertFalse(classic_tournament_mask(picks,teams,positions,max_from_team=4)[0])
        teams[6]='B'
        self.assertTrue(classic_tournament_mask(picks,teams,positions,max_from_team=4)[0])

    def test_batched_fanduel_field_reaches_target_with_legal_rosters(self):
        from test_candidates import fixture
        from simmah_classic_field import build_fanduel_full_field
        pool,_,roster=fixture('FD');pool['Projection']=pool.Salary/500
        slots=[s for s,_ in roster];slots[-1]='D'
        weights=np.linspace(.1,1,len(pool))
        result=build_fanduel_full_field(pool,weights,slots,1000,rng=np.random.default_rng(42))
        self.assertEqual(len(result),1000)
        meta=pool.set_index('Name');index={n:i for i,n in enumerate(pool.Name)}
        picks=np.array([[index[n] for n in row] for row in result[slots].itertuples(index=False,name=None)])
        self.assertTrue(classic_tournament_mask(picks,pool.Team,pool.Position,max_from_team=4).all())
        self.assertTrue(result.Salary.between(59000,60000).all())
        np.testing.assert_array_equal(result.Salary,pool.Salary.to_numpy()[picks].sum(axis=1))
        np.testing.assert_allclose(result.ProjectedPoints,np.round(pool.Projection.to_numpy()[picks].sum(axis=1),2))
        for slot,names in result[slots].items():
            allowed={'RB','WR','TE'} if slot=='FLEX' else {'DST','D','DEF'} if slot=='D' else {slot.rstrip('123')}
            self.assertTrue(meta.loc[names,'Position'].isin(allowed).all())

    def test_batched_draftkings_uses_its_cap_and_full_target(self):
        from test_candidates import fixture
        from simmah_classic_field import build_full_roster_field
        pool,_,roster=fixture();pool['Projection']=pool.Salary/500
        slots=[s for s,_ in roster]
        result=build_full_roster_field(pool,np.ones(len(pool)),slots,1000,
            rng=np.random.default_rng(17),platform='DraftKings')
        self.assertEqual(len(result),1000)
        index={n:i for i,n in enumerate(pool.Name)}
        picks=np.array([[index[n] for n in row] for row in result[slots].itertuples(index=False,name=None)])
        self.assertTrue(classic_tournament_mask(picks,pool.Team,pool.Position).all())
        self.assertTrue(result.Salary.between(47000,50000).all())
        np.testing.assert_array_equal(result.Salary,pool.Salary.to_numpy()[picks].sum(axis=1))
        self.assertEqual(result.attrs['platform'],'DraftKings')
        canonical=result[slots].apply(lambda row:tuple(sorted(row)),axis=1)
        self.assertGreater(canonical.nunique(),.95*len(result))

    def test_field_weights_are_invariant_to_normalization(self):
        import pandas as pd
        from test_candidates import fixture
        from simmah_classic_field import build_full_roster_field
        for site in ['FanDuel','DraftKings']:
            pool,_,roster=fixture('FD' if site=='FanDuel' else 'DK')
            pool['Projection']=pool.Salary/500
            weights=np.linspace(.01,1,len(pool))**2
            slots=[s for s,_ in roster]
            raw=build_full_roster_field(pool,weights,slots,200,rng=np.random.default_rng(19),platform=site)
            normalized=build_full_roster_field(pool,weights/weights.sum(),slots,200,rng=np.random.default_rng(19),platform=site)
            pd.testing.assert_frame_equal(raw,normalized)

    def test_historical_salary_mix_corrects_proposal_frequency(self):
        from test_candidates import fixture
        from simmah_classic_field import build_full_roster_field
        pool,_,roster=fixture('FD');pool['Projection']=pool.Salary/500
        result=build_full_roster_field(pool,np.ones(len(pool)),[s for s,_ in roster],4000,
            rng=np.random.default_rng(87),salary_counts={"60000":1,"59500":1})
        self.assertTrue(result.Salary.isin([60000,59500]).all())
        self.assertAlmostEqual(float((result.Salary==60000).mean()),.5,delta=.04)
        # A broad synthetic pool should not collapse into repeated draws
        # from each small proposal batch.
        canonical=result[[s for s,_ in roster]].apply(lambda row:tuple(sorted(row)),axis=1)
        self.assertGreater(canonical.nunique(),.95*len(result))
        index={name:i for i,name in enumerate(pool.Name)}
        picks=np.array([[index[name] for name in row] for row in result[[s for s,_ in roster]].itertuples(index=False,name=None)])
        self.assertTrue(classic_tournament_mask(picks,pool.Team,pool.Position,max_from_team=4).all())

    def test_empty_batches_are_supported(self):
        self.assertEqual(len(classic_tournament_mask(np.empty((0,9),int),[],[])),0)

if __name__=='__main__':unittest.main()
