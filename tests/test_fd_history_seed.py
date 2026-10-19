"""Verify deployed FD history selects and feeds the full-roster generator."""
import json
from pathlib import Path
import unittest
import numpy as np
from simmah_contest_history import matching_profiles
from simmah_field_construction import learned_construction_distribution,allocate_counts
from simmah_classic_field import build_full_roster_field
from test_candidates import fixture


class FanDuelHistorySeedTest(unittest.TestCase):
    def test_ten_game_history_drives_exact_joint_construction_quotas(self):
        store=json.loads(Path('data/field_history_seed.json').read_text())
        profiles=matching_profiles(store,'FanDuel','Full Roster',fee=.25,max_entries=150,roster_size=9,game_count=10)
        self.assertTrue(profiles)
        distribution=learned_construction_distribution(profiles)
        self.assertIsNotNone(distribution)
        pool,_,roster=fixture('FD');pool['Projection']=pool.Salary/500
        teams=sorted(pool.Team.unique());opponents={team:teams[i^1] for i,team in enumerate(teams)}
        pool['Opponent']=pool.Team.map(opponents)
        field=build_full_roster_field(pool,np.ones(len(pool)),[s for s,_ in roster],1000,
            rng=np.random.default_rng(42),construction_distribution=distribution)
        np.testing.assert_array_equal(np.bincount(field['Construction Group'],minlength=6),allocate_counts(distribution,1000))
        two=matching_profiles(store,'FanDuel','Full Roster',fee=.25,max_entries=150,roster_size=9,game_count=2)
        self.assertFalse(set(p['id'] for p in profiles)&set(p['id'] for p in two))
        self.assertEqual(len({p['id'] for p in store['contests']}),len(store['contests']))
