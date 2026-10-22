"""Frozen event-ledger regression against the pre-optimization engine."""
import hashlib
import unittest
import numpy as np
from simmah_nba_engine import simulate_game,EventRates

EXPECTED = {'DraftKings/weighted': 'e2112eea90d47bd8fdc90908eea951ac096b40a5aa9dc12e86e099135ac2087d', 'DraftKings/zero': '4f0fc57eb9d3fd3b0941642e770a5e4ebdf9da7de9daecd120ce116a0c85e5ad', 'DraftKings/single': '76fcd8429260edf58f513110e554462521f2839a6713f128b88ae8fce66dbe56', 'FanDuel/weighted': '7dc18424450a186d306b636dafa92eb997ed7c77939ff4501accf34432456966', 'FanDuel/zero': 'd2e161638197859ffb0d9ba4a89990031ac83588d2d3c9a7f50bb0f048b9ab24', 'FanDuel/single': '373820f8db2d75891e23c3f276f1c1466c48a6dc2b186c45935fe6740347efab'}

class EventSelectionRegressionTests(unittest.TestCase):
    def test_weighted_zero_and_excluded_role_events_are_unchanged(self):
        for label,expected in EXPECTED.items():
            platform,case=label.split('/')
            with self.subTest(platform=platform,case=case):
                rotations=np.broadcast_to(np.arange(10).reshape(1,2,1,5),(31,2,48,5)).copy()
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
