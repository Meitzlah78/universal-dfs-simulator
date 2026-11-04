"""Frozen event-ledger regression against the pre-optimization engine."""
import hashlib
import unittest
import numpy as np
from simmah_nba_engine import simulate_game,EventRates

EXPECTED = {'DraftKings/weighted': 'e2112eea90d47bd8fdc90908eea951ac096b40a5aa9dc12e86e099135ac2087d', 'DraftKings/zero': '4f0fc57eb9d3fd3b0941642e770a5e4ebdf9da7de9daecd120ce116a0c85e5ad', 'DraftKings/single': '76fcd8429260edf58f513110e554462521f2839a6713f128b88ae8fce66dbe56', 'FanDuel/weighted': '7dc18424450a186d306b636dafa92eb997ed7c77939ff4501accf34432456966', 'FanDuel/zero': 'd2e161638197859ffb0d9ba4a89990031ac83588d2d3c9a7f50bb0f048b9ab24', 'FanDuel/single': '373820f8db2d75891e23c3f276f1c1466c48a6dc2b186c45935fe6740347efab'}

LARGE_EXPECTED = {'DraftKings/weighted': '5ed9dfc737cc4e720f1060eba72cabf47168b1c05c0971b4fbb636b562e245c5', 'DraftKings/zero': 'e9fddec3b0e4e7a09357187bdd663551a752b837ed16c40b613acf025bfe3553', 'DraftKings/single': 'b4bc4633ca046650228ba9bfc8f457d1b6ed6a075331725e345d1c4f6f4268f2', 'FanDuel/weighted': '4ae9705b2ac48aa29e32cd40f8d1b8f718160ad7e4553e6c1145b0551af787c2', 'FanDuel/zero': 'f9755b9f28f47b5392bbaaa2d5cf919c40133f96cb0f4e656c0d30048d0e00c3', 'FanDuel/single': 'e2344df24313c2afdea695dd4117372c7f5d01cdf90f031557a907050a04a75b'}

class EventSelectionRegressionTests(unittest.TestCase):
    def check_ledgers(self,expected_ledgers,n):
        for label,expected in expected_ledgers.items():
            platform,case=label.split('/')
            with self.subTest(platform=platform,case=case):
                rotations=np.broadcast_to(np.arange(10).reshape(1,2,1,5),(n,2,48,5)).copy()
                weights=np.random.default_rng(23).random((2,5,5))
                if case=='zero':weights[:]=0
                if case=='single':weights[:]=0;weights[:,0,:]=1
                rates=[EventRates(.12,.1,.4,.53,.36,.78,.6,.25,.6,.1,13)]*2
                result=simulate_game(rotations,weights,rates,37,platform=platform)
                digest=hashlib.sha256()
                for key in ('stats','scores','team_points','overtime_periods','elapsed_seconds'):
                    digest.update(np.ascontiguousarray(result[key]).tobytes())
                for key in sorted(result['counters']):digest.update(result['counters'][key].tobytes())
                self.assertEqual(digest.hexdigest(),expected)


    def test_weighted_zero_and_excluded_role_events_are_unchanged(self):
        self.check_ledgers(EXPECTED,31)

    def test_large_batches_preserve_event_ledgers_across_fast_path(self):
        self.check_ledgers(LARGE_EXPECTED,513)
