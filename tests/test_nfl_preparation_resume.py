"""Interrupted preparation must resume without changing seeded fitted results."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from simmah_nfl_engine import simulate_stat_lines
from simmah_nfl_scoring import score_nfl_stat_line
from simmah_projection_inputs import fit_projection_inputs
from simmah_simulation_store import prepare_simulations, CacheIntegrityError
from test_nfl_engine import fixture


class PreparationResumeTest(unittest.TestCase):
    def test_implementation_revision_preserves_scientific_model_and_validation(self):
        from simmah_nfl_learning import model_for_date,engine_digest,digest
        registry=json.loads(Path('data/nfl_models/index.json').read_text())
        item=registry['versions'][0]
        model=model_for_date((pd.Timestamp(item['validation_through'])+pd.Timedelta(days=1)).date().isoformat())
        self.assertEqual(model['engine_sha256'],engine_digest())
        proof=model['implementation_revalidation']
        parent=json.loads((Path('data/nfl_models/versions')/(model['parent_version']+'.json')).read_text())
        self.assertEqual(digest(parent),proof['source_model_sha256'])
        for key in parent:
            if key not in {'engine_sha256','version','parent_version','implementation_revalidation'}:self.assertEqual(model[key],parent[key],key)
        raw=Path(proof['evidence']).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),proof['evidence_sha256'])
        evidence=json.loads(raw)
        self.assertEqual(evidence['new_engine_sha256'],engine_digest())
        self.assertFalse(evidence['holdout_retested'])

    def test_resume_matches_full_fit_and_skips_finished_passes(self):
        pool,roles=fixture();states=[]
        expected,report=fit_projection_inputs(pool,roles,'DraftKings',score_nfl_stat_line,pilot_n=32,iterations=2)
        def stop(state):
            states.append(copy.deepcopy(state))
            raise RuntimeError('cancelled')
        with self.assertRaisesRegex(RuntimeError,'cancelled'):
            fit_projection_inputs(pool,roles,'DraftKings',score_nfl_stat_line,pilot_n=32,iterations=2,save_state=stop)
        with patch('simmah_nfl_engine.simulate_stat_lines',wraps=simulate_stat_lines) as engine:
            actual,resumed=fit_projection_inputs(pool,roles,'DraftKings',score_nfl_stat_line,pilot_n=32,iterations=2,resume_state=states[-1])
            self.assertEqual(engine.call_count,2)
        self.assertEqual(actual,expected);pd.testing.assert_frame_equal(report,resumed)

    def test_final_market_fit_resume_does_not_repeat_initial_or_market_work(self):
        from pathlib import Path
        pool,roles=fixture()
        kwargs=dict(count=16,pilot_n=16,iterations=1,market_targets={'A':(20.,)})
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as full:
            original=fit_projection_inputs
            def interrupted(*args,**kw):
                if kw.get('market_gain'):
                    save=kw['save_state']
                    def stop(state):save(state);raise RuntimeError('cancelled')
                    kw['save_state']=stop
                return original(*args,**kw)
            with patch('simmah_market_calibration.calibrate_market_inputs',return_value=({'A':1.1},[])):
                expected=prepare_simulations(pool,roles,'FanDuel',full,**kwargs)
                with patch('simmah_simulation_store.fit_projection_inputs',side_effect=interrupted):
                    with self.assertRaisesRegex(RuntimeError,'cancelled'):
                        prepare_simulations(pool,roles,'FanDuel',root,**kwargs)
            with patch('simmah_market_calibration.calibrate_market_inputs',side_effect=AssertionError('market repeated')), \
                 patch('simmah_nfl_engine.simulate_stat_lines',wraps=simulate_stat_lines) as engine:
                actual=prepare_simulations(pool,roles,'FanDuel',root,**kwargs)
                self.assertEqual(engine.call_count,1)
            for kind in ['evaluation','construction','fit_report']:
                pd.testing.assert_frame_equal(actual[kind],expected[kind])
            checkpoint=next((Path(root)/'fit_progress').glob('*/initial.json'))
            # A different prepared-outcome seed still reuses the finalized fit.
            checkpoint.write_text('invalid')
            with patch('simmah_simulation_store.fit_projection_inputs',side_effect=AssertionError('refit')):
                prepare_simulations(pool,roles,'FanDuel',root,**dict(kwargs,evaluation_seed=11,construction_seed=12))

    def test_corrupt_partial_checkpoint_is_rejected(self):
        from pathlib import Path
        pool,roles=fixture()
        with tempfile.TemporaryDirectory() as root:
            def interrupted(*args,**kw):
                save=kw['save_state']
                def stop(state):save(state);raise RuntimeError('cancelled')
                kw['save_state']=stop
                return fit_projection_inputs(*args,**kw)
            with patch('simmah_simulation_store.fit_projection_inputs',side_effect=interrupted):
                with self.assertRaises(RuntimeError):prepare_simulations(pool,roles,'FanDuel',root,count=16,pilot_n=16,iterations=1)
            next((Path(root)/'fit_progress').glob('*/initial.json')).write_text('{}')
            with self.assertRaises(CacheIntegrityError):prepare_simulations(pool,roles,'FanDuel',root,count=16,pilot_n=16,iterations=1)

    def test_progress_labels_both_fits_and_does_not_move_backwards(self):
        pool,roles=fixture();messages=[]
        with tempfile.TemporaryDirectory() as root, patch('simmah_market_calibration.calibrate_market_inputs',return_value=({'A':1.1},[])):
            prepare_simulations(pool,roles,'FanDuel',root,count=16,pilot_n=16,iterations=1,
                                market_targets={'A':(20.,)},progress=lambda f,t:messages.append((f,t)))
        self.assertEqual(sorted(f for f,t in messages),[f for f,t in messages])
        self.assertTrue(any('(1/2)' in t for f,t in messages))
        self.assertTrue(any('(2/2)' in t for f,t in messages))
        self.assertTrue(any('fit ETA' in t for f,t in messages))

    def test_completed_evaluation_survives_cancelled_construction(self):
        from pathlib import Path
        pool,roles=fixture();kwargs=dict(count=32,pilot_n=16,iterations=0)
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as full:
            expected=prepare_simulations(pool,roles,'DraftKings',full,**kwargs)
            calls=[]
            def interrupted(*args,**kw):
                calls.append(1)
                if len(calls)==2:raise RuntimeError('cancelled construction')
                return simulate_stat_lines(*args,**kw)
            with patch('simmah_simulation_store.simulate_stat_lines',side_effect=interrupted):
                with self.assertRaisesRegex(RuntimeError,'cancelled construction'):
                    prepare_simulations(pool,roles,'DraftKings',root,**kwargs)
            self.assertTrue(list((Path(root)/'prepared').glob('*/evaluation.json')))
            with patch('simmah_simulation_store.simulate_stat_lines',wraps=simulate_stat_lines) as engine, \
                 patch('simmah_simulation_store.fit_projection_inputs',side_effect=AssertionError('refit')):
                actual=prepare_simulations(pool,roles,'DraftKings',root,**kwargs)
                self.assertEqual(engine.call_count,1)
            for kind in ['evaluation','construction','fit_report']:
                pd.testing.assert_frame_equal(actual[kind],expected[kind])
            self.assertFalse(list((Path(root)/'prepared').glob('*/evaluation.json')))

    def test_corrupt_evaluation_checkpoint_is_rejected(self):
        from pathlib import Path
        pool,roles=fixture();kwargs=dict(count=16,pilot_n=16,iterations=0)
        with tempfile.TemporaryDirectory() as root:
            calls=[]
            def interrupted(*args,**kw):
                calls.append(1)
                if len(calls)==2:raise RuntimeError('cancelled')
                return simulate_stat_lines(*args,**kw)
            with patch('simmah_simulation_store.simulate_stat_lines',side_effect=interrupted):
                with self.assertRaises(RuntimeError):prepare_simulations(pool,roles,'FanDuel',root,**kwargs)
            next((Path(root)/'prepared').glob('*/evaluation.npz')).write_bytes(b'corrupt')
            with self.assertRaises(CacheIntegrityError):prepare_simulations(pool,roles,'FanDuel',root,**kwargs)


if __name__=='__main__':unittest.main()
