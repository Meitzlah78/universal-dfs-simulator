import unittest
import numpy as np
from simmah_nba_verified_minutes_offline import eligibility_at, verified_history, age_shrink, bounded_redistribution, learn_role_bounds, forecast_verified_team

class VerifiedMinutesTests(unittest.TestCase):
    def test_event_season_overrides_league_header(self):
        from scripts.recover_nba_season_metadata_offline import extract_events
        payload={'leagues':[{'season':{'type':2}}], 'events':[{'id':'1','season':{'year':2027,'type':1,'slug':'preseason'}}]}
        result=extract_events(payload,'source')['1']
        self.assertEqual(result['season_type_slug'],'preseason')
        self.assertTrue(result['season_verified'])

    def test_old_history_expires_even_when_mean_unchanged(self):
        row={'completed_at':'2026-10-01T00:00Z','minutes':30}
        fresh=age_shrink([row],10,'2026-10-02T00:00Z')
        stale=age_shrink([row],10,'2027-10-02T00:00Z')
        self.assertEqual(fresh['history_mean'],stale['history_mean'])
        self.assertLess(stale['history_weight'],fresh['history_weight'])
        self.assertAlmostEqual(stale['raw_minutes'],10,places=6)
    def test_unknown_is_not_ineligible(self):
        self.assertEqual(eligibility_at(None,'2026-11-01T00:00Z','MIL'),'unknown')
        e=dict(source='dated roster',published_at='2026-11-02T00:00Z',valid_from='2026-10-01T00:00Z',valid_until='2026-12-01T00:00Z',team='MIL',eligibility='eligible')
        self.assertEqual(eligibility_at(e,'2026-11-01T00:00Z','MIL'),'unknown')
    def test_metadata_and_participation_required(self):
        base=dict(date='2026-10-01',completed_at='2026-10-02T00:00Z',minutes=0,season_verified=True,season_source='source',season_id='2027',season_type='regular',participation='unknown')
        accepted,rejected=verified_history([base],'2026-11-01T00:00Z','2026-11-01')
        self.assertFalse(accepted)
        self.assertEqual(rejected[0]['rejection'],'unknown_participation')
        base['participation']='confirmed_dnp'
        self.assertEqual(len(verified_history([base],'2026-11-01T00:00Z','2026-11-01')[0]),1)
    def test_role_bounds_not_universal_cap(self):
        rows=[dict(role='core',role_verified_pregame=True,minutes=39+i%4,date='2026-10-01') for i in range(24)]
        self.assertGreater(learn_role_bounds(rows,'core')['upper'],38)
        with self.assertRaises(ValueError):learn_role_bounds(rows,'bench')
    def test_conservation_and_uncertainty(self):
        means=[30]*8
        out=bounded_redistribution(means,[0]*8,[42]*4+[25]*4,[1]*4+[2]*4)
        self.assertAlmostEqual(sum(out),240)
        self.assertTrue(np.all(out[4:]<=25))
        self.assertTrue(np.all(out[:4]>30))
    def test_infeasible_bounds_reported(self):
        with self.assertRaisesRegex(ValueError,'no bounds relaxed'):
            bounded_redistribution([30]*8,[0]*8,[29]*8,[1]*8)
    def test_integrated_verified_arm_and_unknown_blocker(self):
        history=[];roster=[]
        for i in range(8):
            key=[str(i),'MIL']
            roster.append(dict(name=str(i),team='MIL',key=key,
                eligibility_evidence=dict(source='dated roster',published_at='2026-10-31T00:00Z',valid_from='2026-10-31T00:00Z',valid_until='2026-11-02T00:00Z',team='MIL',eligibility='eligible'),
                role_prior=dict(source='earlier training',published_at='2026-10-31T00:00Z',valid_from='2026-10-31T00:00Z',valid_until='2026-11-02T00:00Z',role='rotation',minutes=30,uncertainty=2)))
            for j in range(4):
                history.append(dict(key=key,date='2026-10-01',completed_at='2026-10-02T00:00Z',minutes=26+j*3,season_verified=True,season_source='event',season_id='2027',season_type='regular',participation='played',role='rotation',role_verified_pregame=True))
        result=forecast_verified_team(roster,history,'2026-11-01','2026-11-01T00:00Z')
        self.assertAlmostEqual(sum(p['predicted_minutes'] for p in result['players']),240)
        roster[0]['eligibility_evidence']=None
        with self.assertRaisesRegex(ValueError,'Unverified roster eligibility'):
            forecast_verified_team(roster,history,'2026-11-01','2026-11-01T00:00Z')

    def test_future_history_rejected(self):
        with self.assertRaises(ValueError):age_shrink([{'completed_at':'2026-12-01T00:00Z','minutes':20}],10,'2026-11-01T00:00Z')

if __name__=='__main__':unittest.main()
