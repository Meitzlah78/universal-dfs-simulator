import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from scripts.replay_nfl_four_arm_research import checked_baseline

class ResearchGateTests(unittest.TestCase):
    def test_failed_slice_blocks_before_any_candidate_reads(self):
        with TemporaryDirectory() as d:
            Path(d,'validation.json').write_text(json.dumps({'research_baseline_locked':False,'slice_gate':False,'ledger_max_error':0}))
            with self.assertRaisesRegex(ValueError,'ablations blocked'):checked_baseline(d)
    def test_wrong_policy_or_scope_cannot_unlock_matrix(self):
        with TemporaryDirectory() as d:
            Path(d,'validation.json').write_text(json.dumps({'research_baseline_locked':True,'slice_gate':True,'ledger_max_error':0,'policy':'unverified','games':285,'draws_per_game':1024}))
            with self.assertRaisesRegex(ValueError,'scope mismatch'):checked_baseline(d)

    def test_missing_or_failed_offensive_timeout_check_blocks_matrix(self):
        from simmah_nfl_clock_rebuild_offline import POLICY_VERSION
        checks={f'q{q}_{m}':{'pass':True} for q in [2,4] for m in ['snaps','defensive_timeouts']}
        for offensive in [None,{'pass':False}]:
            with TemporaryDirectory() as d:
                c=dict(checks)
                if offensive is not None:c['q2_offensive_timeouts']=offensive
                Path(d,'validation.json').write_text(json.dumps({'research_baseline_locked':True,'slice_gate':True,'ledger_max_error':0,'policy':POLICY_VERSION,'games':285,'draws_per_game':1024,'checks':c}))
                with self.assertRaisesRegex(ValueError,'offensive timeout'):checked_baseline(d)
