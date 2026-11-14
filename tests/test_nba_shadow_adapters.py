from copy import deepcopy
import unittest
from simmah_nba_shadow_adapters import run_team,allocate
from tests.nba_shadow_adapter_fixture import fixture,capture,TEAM,GAME

class AdapterTests(unittest.TestCase):
    def execute(self,roster=None,history=None):
        c,q,r,p=capture(roster,history);return run_team(c,q,r,p)
    def test_complete_synthetic_team_forecasts_conserve_240(self):
        result=self.execute();self.assertEqual(result['status'],'forecasts')
        self.assertEqual(len(result['predictions']),8)
        self.assertAlmostEqual(sum(p['predicted_minutes'] for p in result['predictions']),240)
        self.assertEqual(len({p['player_id'] for p in result['predictions']}),8)
        self.assertFalse(result['qualified_for_evaluation']);self.assertEqual(result['provenance'],'synthetic')
    def test_known_inactive_creates_quantified_bound_conflict(self):
        r,h=fixture();r['players'][-1]['eligibility']='ineligible'
        result=self.execute(r,h);self.assertEqual(result['status'],'allocation_conflict')
        self.assertEqual(result['allocation_conflict']['upper_minute_deficit'],30)
        self.assertFalse(result['allocation_conflict']['bounds_relaxed'])
    def test_name_cannot_repair_invalid_player_id(self):
        r,h=fixture();r['players'][0]['player_id']='Identical names are irrelevant'
        self.assertEqual(self.execute(r,h)['reason'],'INVALID_STABLE_ID')
    def test_omitted_roster_member_blocks_whole_pool(self):
        r,h=fixture();r['players'].pop()
        self.assertEqual(self.execute(r,h)['reason'],'ROSTER_MANIFEST_MISMATCH')
    def test_unknown_status_is_not_removed(self):
        r,h=fixture();r['players'][0]['eligibility']='unknown'
        out=self.execute(r,h);self.assertEqual(out['reason'],'UNRESOLVED_ELIGIBILITY')
        self.assertIsNone(out['predictions'])
    def test_cold_start_receives_no_number(self):
        r,h=fixture();h['records']=[row for row in h['records'] if row['player_id']!='1001']
        out=self.execute(r,h);self.assertEqual(out['reason'],'COLD_START_ROLE_HISTORY')
        self.assertNotIn('minutes',out['details']);self.assertIsNone(out['predictions'])
    def test_traded_player_does_not_inherit_old_team_role(self):
        r,h=fixture();r['team_id']='1610612747'
        for p in r['players']:p['team_id']=r['team_id']
        self.assertEqual(self.execute(r,h)['reason'],'COLD_START_ROLE_HISTORY')
    def test_receipt_at_capture_is_too_late(self):
        c,q,r,p=capture();r[q['roster_sha256']]['observed_at']=c['frozen_at']
        self.assertEqual(run_team(c,q,r,p)['reason'],'SOURCE_NOT_OBSERVED_BEFORE_CAPTURE')
    def test_post_capture_status_rejected(self):
        r,h=fixture();r['players'][0]['status_observed_at']='2026-11-14T18:01:00Z'
        self.assertEqual(self.execute(r,h)['reason'],'STATUS_NOT_OBSERVED_BEFORE_CAPTURE')
    def test_naive_time_not_assumed_UTC(self):
        r,h=fixture();r['players'][0]['status_observed_at']='2026-11-14T17:55:00'
        self.assertEqual(self.execute(r,h)['reason'],'INVALID_OR_NAIVE_TIMESTAMP')
    def test_unapproved_source_cannot_assert_itself_certified(self):
        c,q,r,p=capture();r[q['roster_sha256']]['source']='https://unapproved.example/roster'
        self.assertEqual(run_team(c,q,r,p)['reason'],'UNAPPROVED_SOURCE_PROFILE')
    def test_target_future_and_end_equal_cutoff_do_not_change_forecasts(self):
        r,h=fixture();base=self.execute(r,h)['predictions']
        for gid,end in [(GAME,'2026-11-14T17:00:00Z'),('0022600100','2026-11-14T18:00:00Z'),('0022600101','2026-11-15T23:00:00Z')]:
            row=deepcopy(h['records'][0]);row.update(game_id=gid,game_end_time=end,minutes=48.)
            h['records'].append(row)
        out=self.execute(r,h);self.assertEqual(out['predictions'],base)
        self.assertEqual(out['history_rejections']['not_completed_before_capture'],3)
    def test_unknown_zero_is_excluded_not_DNP(self):
        r,h=fixture();row=deepcopy(h['records'][0]);row.update(game_id='0022599999',minutes=0,participation='unknown')
        h['records'].append(row)
        self.assertEqual(self.execute(r,h)['history_rejections']['unknown_participation'],1)
    def test_promotion_has_no_normal_bound_fallback(self):
        r,h=fixture();r['players'][0]['role_context']='injury_promoted'
        out=self.execute(r,h);self.assertEqual(out['reason'],'INSUFFICIENT_CONTEXT_TRAINING')
        self.assertEqual(out['details']['context'],'injury_promoted')
    def test_duplicate_history_not_double_weighted(self):
        r,h=fixture();h['records'].append(deepcopy(h['records'][0]))
        self.assertEqual(self.execute(r,h)['reason'],'DUPLICATE_HISTORY_OBSERVATION')
    def test_malformed_roster_is_explicitly_unsupported(self):
        r,h=fixture();r['players']=[None]
        self.assertEqual(self.execute(r,h)['reason'],'MALFORMED_ADAPTER_INPUT')

    def test_no_universal_38_minute_cap(self):
        f=[{'raw_minutes':40.,'lower':39.,'upper':42.,'uncertainty':1.} for _ in range(6)]
        out,conflict=allocate(f);self.assertIsNone(conflict)
        self.assertTrue(all(p['predicted_minutes']>38 for p in out))

if __name__=='__main__':unittest.main()
