"""Evidence must survive preparation without being copied into every row."""
import unittest
from unittest.mock import patch
import pandas as pd
from simmah_nba_frame import data_view
from simmah_nba_pregame import ROLE_COLUMNS
from simmah_nba_role_priors import apply_position_priors
from simmah_nba_game_context import restore_saved_game_metadata
from simmah_nba_markets import extract_markets


class Evidence(dict):
    copies = 0

    def __deepcopy__(self, memo):
        type(self).copies += 1
        return type(self)(self)


class PreparationMetadataTests(unittest.TestCase):
    def pool(self):
        pool = pd.DataFrame([{'Player ID':str(i), 'Name':'Player '+str(i),
            'Position':'PG', 'Team':'NY' if i<5 else 'BOS',
            'Opponent':'BOS' if i<5 else 'NY', 'Salary':5000,
            'Projection':12., 'Projected Minutes':24., 'Projection Source':'RotoWire',
            'Injury Status':'Active', **{c:0. for c in ROLE_COLUMNS}}
            for i in range(10)])
        pool.attrs['provider_evidence'] = Evidence(payload=['raw'] * 1000)
        return pool

    def test_read_view_preserves_nullable_dtypes_and_avoids_evidence_copies(self):
        pool=self.pool();pool['Nullable']=pd.array([None]*10,dtype='Int64')
        Evidence.copies=0
        view=data_view(pool)
        self.assertEqual(view.attrs,{})
        list(view.iterrows())
        self.assertEqual(Evidence.copies,0)
        pd.testing.assert_frame_equal(view,pool)
        self.assertIn('provider_evidence',pool.attrs)

    def test_role_values_and_evidence_match_original_row_path(self):
        pool=self.pool()
        model={'before':'2026-04-09','latest_game':'2026-04-08',
               'positions':{'G':{'rates':[.4,.2,.1,.02,.01]}}}
        Evidence.copies=0
        with patch('simmah_nba_role_priors.data_view',side_effect=lambda p:p), \
             patch('simmah_nba_learning.data_view',side_effect=lambda p:p):
            old=apply_position_priors(pool,model,'2026-10-23')
            old_copies=Evidence.copies
        Evidence.copies=0
        new=apply_position_priors(pool,model,'2026-10-23')
        new_copies=Evidence.copies
        pd.testing.assert_frame_equal(new,old)
        self.assertEqual(new.attrs,old.attrs)
        self.assertLess(new_copies,old_copies)
        self.assertTrue(pool[ROLE_COLUMNS].eq(0).all().all())

    def test_dated_metadata_recovery_and_markets_match_original_path(self):
        current=self.pool();previous=self.pool()
        previous['Game Start']='2026-10-23T19:00:00-04:00'
        previous['Game Total']=230.;previous['Team Implied Points']=115.
        previous['Expected Starter']=True
        with patch('simmah_nba_game_context.data_view',side_effect=lambda p:p):
            old=restore_saved_game_metadata(current,previous,'2026-10-23')
        new=restore_saved_game_metadata(current,previous,'2026-10-23')
        pd.testing.assert_frame_equal(new,old)
        self.assertEqual(new.attrs,old.attrs)
        with patch('simmah_nba_markets.data_view',side_effect=lambda p:p):
            expected=extract_markets(old)
        self.assertEqual(extract_markets(new),expected)
        self.assertNotIn('Game Start',current)
        self.assertEqual(new.attrs['provider_evidence'],current.attrs['provider_evidence'])
