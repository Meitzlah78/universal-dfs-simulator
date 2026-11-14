import json
import tempfile
import unittest
from simmah_nba_shadow_minutes_offline import assess_shadow,cold_start_policy,write_shadow_capture

class ShadowTests(unittest.TestCase):
    def snapshot(self):
        return {'game_id':'g','team':'MIL','captured_at':'2026-11-14T18:00Z','scheduled_tipoff':'2026-11-14T23:00Z',
            'receipts':[dict(source_id='r',source='fixture',observed_at='2026-11-14T17:59Z',sha256='a'*64)],
            'pool_evidence':dict(scope='full_team_game_roster',member_player_ids=[str(i) for i in range(8)],membership_verified=True,eligibility_semantics_verified=True,verifier_reference='fixture-approved-adapter',source_id='r',game_id='g',team='MIL'),
            'players':[dict(player_id=str(i),source_id='r',eligibility='eligible',role_prior=dict(supported=True,minutes=30,source='past-history',as_of='2026-11-14T17:59Z',latest_training_completion='2026-11-13T23:00Z')) for i in range(8)]}
    def test_verified_inputs_still_wait_for_actual_tip(self):
        s=self.snapshot();self.assertEqual(assess_shadow(s)['evaluation_status'],'pending_actual_tipoff')
        self.assertEqual(assess_shadow(s,actual_tipoff='2026-11-14T23:10Z')['evaluation_status'],'evaluable')
    def test_late_receipt_blocks(self):
        s=self.snapshot();s['receipts'][0]['observed_at']='2026-11-14T18:01Z'
        self.assertFalse(assess_shadow(s)['pregame_inputs_verified'])
    def test_supported_priors_do_not_certify_roster(self):
        s=self.snapshot();s['pool_evidence']['membership_verified']=False
        self.assertFalse(assess_shadow(s)['pregame_inputs_verified'])
    def test_no_numeric_cold_start_fill(self):
        self.assertNotIn('minutes',cold_start_policy({'supported':False}))
        s=self.snapshot();s['players'][0]['role_prior']={'supported':False}
        self.assertIn('unsupported_role_prior',assess_shadow(s)['errors'])
    def test_known_ineligible_player_needs_no_prior(self):
        s=self.snapshot();s['players'][0]['eligibility']='ineligible';s['players'][0].pop('role_prior')
        self.assertTrue(assess_shadow(s)['pregame_inputs_verified'])
    def test_omitting_one_unknown_player_cannot_certify_subset(self):
        s=self.snapshot();s['players'].pop()
        self.assertIn('roster_membership_manifest_mismatch',assess_shadow(s)['errors'])

    def test_unknown_is_not_removed(self):
        s=self.snapshot();s['players'][0]['eligibility']='unknown'
        self.assertFalse(assess_shadow(s)['pregame_inputs_verified'])
    def test_actual_tip_can_invalidate_scheduled_assumption(self):
        self.assertEqual(assess_shadow(self.snapshot(),actual_tipoff='2026-11-14T17:59Z')['evaluation_status'],'capture_not_before_actual_tipoff')
    def test_logging_is_append_only_and_cannot_backdate(self):
        with tempfile.TemporaryDirectory() as root:
            s=self.snapshot();s['scheduled_tipoff']='2099-01-01T00:00Z'
            p=write_shadow_capture(root,s,{'r':{'players':['fixture']}})
            old=p.read_bytes();q=write_shadow_capture(root,s,{'r':{'players':['fixture']}})
            self.assertNotEqual(p,q);self.assertEqual(old,p.read_bytes())
            record=json.loads(old);self.assertNotEqual(record['captured_at'],s['captured_at'])
            self.assertEqual(record['mode'],'shadow')
            self.assertNotEqual(record['receipts'][0]['sha256'],'a'*64)

if __name__=='__main__':unittest.main()
