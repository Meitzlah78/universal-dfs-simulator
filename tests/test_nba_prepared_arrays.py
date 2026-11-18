import unittest
import numpy as np
import pandas as pd
import test_nba_pregame
from simmah_nba_prepared_arrays import prepare_player_arrays,ROLE_COLUMNS
from simmah_nba_pregame import PregameEngine
from simmah_nba_ownership import active_players
from simmah_workspace_backup import pack,unpack


class Evidence(dict):
    def __deepcopy__(self,memo):
        raise AssertionError('Numerical preparation must not copy provider evidence')


class PreparedArrayTests(unittest.TestCase):
    def fixture(self):
        pool,markets,rates=test_nba_pregame.PregameTests().fixture()
        pool.attrs.update(platform='DraftKings',slate_date='2026-11-18')
        return pool,markets,rates

    def test_unchanged_inputs_reuse_readonly_arrays_without_copying_evidence(self):
        pool,_,_=self.fixture();pool.attrs['provider_evidence']=Evidence(raw=['payload']*1000)
        cache={};first=prepare_player_arrays(pool,cache)
        self.assertIs(prepare_player_arrays(pool,cache),first)
        for value in first.values():
            if isinstance(value,np.ndarray):self.assertFalse(value.flags.writeable)
        with self.assertRaises(ValueError):first['projection'][0]=0
        self.assertIn('provider_evidence',pool.attrs)

    def test_input_changes_and_row_order_invalidate(self):
        pool,_,_=self.fixture();pool['Projection']=pool['Projection'].astype(float)
        cache={};original=prepare_player_arrays(pool,cache)
        for column,value in [('Projection',np.nextafter(float(pool.Projection.iloc[0]),np.inf)),
                             ('Projected Minutes',47.),('Injury Status','Out'),
                             ('Eligible',False),('Salary',9999),(ROLE_COLUMNS[0],2.)]:
            with self.subTest(column=column):
                changed=pool.copy();changed.at[0,column]=value
                self.assertNotEqual(prepare_player_arrays(changed,cache)['identity'],original['identity'])
        self.assertNotEqual(prepare_player_arrays(pool.iloc[::-1],cache)['identity'],original['identity'])
        self.assertLessEqual(len(cache),4)

    def test_site_and_date_scope_are_separate_but_raw_evidence_is_not_a_numeric_input(self):
        pool,_,_=self.fixture();cache={};first=prepare_player_arrays(pool,cache)
        pool.attrs['raw_provider_payload']={'raw':['large']*1000}
        self.assertIs(prepare_player_arrays(pool,cache),first)
        pool.attrs['platform']='FanDuel'
        self.assertNotEqual(prepare_player_arrays(pool,cache)['identity'],first['identity'])
        pool.attrs['slate_date']='2026-11-19'
        self.assertEqual(len({row['identity'] for row in cache.values()}),2)
        self.assertNotEqual(prepare_player_arrays(pool,cache)['identity'],first['identity'])

    def test_workspace_roundtrip_preserves_cache_and_refreezes_arrays(self):
        pool,_,_=self.fixture();cache={};first=prepare_player_arrays(pool,cache)
        restored=unpack(pack({'record':{},'checkpoint':{'cache':cache,'pool':pool}}))['checkpoint']
        saved=restored['cache'][first['identity']]
        self.assertIs(prepare_player_arrays(restored['pool'],restored['cache']),saved)
        np.testing.assert_array_equal(saved['roles'],first['roles'])
        self.assertFalse(saved['roles'].flags.writeable)

    def test_cached_and_uncached_engines_produce_exact_same_draws(self):
        for site in ['DraftKings','FanDuel']:
            with self.subTest(site=site):
                pool,markets,rates=self.fixture()
                prepared=prepare_player_arrays(pool,{})
                direct=PregameEngine(pool,markets,rates,platform=site,parallel=False)
                cached=PregameEngine(pool,markets,rates,platform=site,parallel=False,prepared=prepared)
                np.testing.assert_array_equal(direct(64,83),cached(64,83))
                self.assertEqual(direct.rotation_reconciliation,cached.rotation_reconciliation)

    def test_stale_arrays_cannot_hide_new_out_player(self):
        pool,markets,rates=self.fixture();prepared=prepare_player_arrays(pool,{})
        pool.at[0,'Injury Status']='Out'
        np.testing.assert_array_equal(active_players(pool,prepared),prepare_player_arrays(pool)['active'])
        self.assertFalse(active_players(pool,prepared)[0])
        with self.assertRaises(ValueError):
            PregameEngine(pool,markets,rates,prepared=prepared)
