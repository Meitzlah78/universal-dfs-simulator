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
