import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from simmah_nba_shadow_worker import run
from tests.nba_shadow_adapter_fixture import fixture,capture,persist

class AdapterEndToEndTests(unittest.TestCase):
    def test_frozen_subprocess_forecasts_and_canonical_reconciliation_keys(self):
        c,q,r,p=capture()
        with tempfile.TemporaryDirectory() as root:
            baseline=Path(root)/'saved_lineups.json';baseline.write_text('live-portfolio-unchanged')
            path=persist(root,c,p)
            subprocess.run([sys.executable,str(Path(__file__).parents[1]/'simmah_nba_shadow_worker.py'),str(path)],check=True,timeout=20)
            out=json.loads((Path(root)/(c['capture_id']+'.result.json')).read_text())
            self.assertEqual(out['status'],'forecasts');self.assertEqual(out['capture_id'],c['capture_id'])
            self.assertAlmostEqual(sum(p['predicted_minutes'] for p in out['predictions']),240)
            for row in out['predictions']:
                self.assertEqual(row['game_id'],q['game_id']);self.assertEqual(row['team_id'],q['team_id'])
                self.assertIn('player_id',row);self.assertIn('latest_training_end',row)
            self.assertEqual(baseline.read_text(),'live-portfolio-unchanged')
            self.assertFalse(out['qualified_for_evaluation'])
    def test_subprocess_records_exact_conflict_without_live_changes(self):
        roster,history=fixture();roster['players'][-1]['eligibility']='ineligible'
        c,q,r,p=capture(roster,history)
        with tempfile.TemporaryDirectory() as root:
            path=persist(root,c,p);out=run(path)
            self.assertEqual(out['status'],'allocation_conflict')
            self.assertEqual(out['allocation_conflict']['upper_minute_deficit'],30)
            self.assertEqual(len(out['frozen_player_parameters']),7)
            self.assertEqual(out['id_namespace'],'nba')
            self.assertIsNone(out['predictions']);self.assertFalse(out['production_modified'])
    def test_model_hash_change_blocks_forecasts(self):
        c,q,r,p=capture();c['model_source_hashes']['simmah_nba_shadow_adapters.py']='0'*64
        with tempfile.TemporaryDirectory() as root:
            out=run(persist(root,c,p));self.assertEqual(out['reason'],'MODEL_VERSION_NOT_FROZEN')
    def test_duplicate_team_requests_are_both_unsupported(self):
        c,q,r,p=capture();c['adapter_requests'].append(dict(q))
        with tempfile.TemporaryDirectory() as root:
            out=run(persist(root,c,p))
            self.assertEqual(len(out['team_game_results']),2)
            self.assertTrue(all(r['reason']=='DUPLICATE_TEAM_GAME_REQUEST' for r in out['team_game_results']))

    def test_malformed_request_is_recorded_not_silently_dropped(self):
        c,q,r,p=capture();c['adapter_requests']=[{'game_id':[]}]
        with tempfile.TemporaryDirectory() as root:
            out=run(persist(root,c,p));self.assertEqual(out['reason'],'MALFORMED_ADAPTER_REQUEST')

    def test_receipt_tampering_cannot_produce_results(self):
        c,q,r,p=capture()
        with tempfile.TemporaryDirectory() as root:
            path=persist(root,c,p);(Path(root)/(q['roster_sha256']+'.response.gz')).write_bytes(b'tampered')
            with self.assertRaises(Exception):run(path)
            self.assertFalse((Path(root)/(c['capture_id']+'.result.json')).exists())

if __name__=='__main__':unittest.main()
