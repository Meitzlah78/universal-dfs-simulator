import unittest,json,hashlib,csv,io
from copy import deepcopy
from simmah_ownership_ingest import ingest_ownership,require_calibratable,OwnershipIngestionError,TIMESTAMPS

class IngestionTests(unittest.TestCase):
    def fixtures(self):
        ids=[str(i) for i in range(6)]
        slate={'site_id':'fd','slate_id':'slate','game_set_id':'game','expected_game_set':['A@B'],'player_ids':ids,'candidate_excluded_ids':['0']}
        meta={'site_id':'fd','slate_id':'slate','game_set_id':'game','observed_game_set':['A@B'],'source_url_or_id':'test endpoint',
          'feed_name':'synthetic-test','unit':'probability','request_status':'success','target_kind':'projected','source_slate_key':'slate','matching_logic_version':'exact-v1',
          'request_started_utc':'2026-10-22T15:00:00Z','request_completed_utc':'2026-10-22T15:01:00Z','last_successful_received_utc':'2026-10-22T15:01:00Z','provider_updated_utc':None,'lock_time_utc':'2026-10-22T23:00:00Z'}
        rows=[{**{k:slate[k] for k in ['site_id','slate_id','game_set_id']},'player_id':i,'target_ownership_cpt':1/6,'target_ownership_flex':5/6} for i in ids]
        return slate,meta,rows
    def run_feed(self,slate,meta,rows,format='json'):
        if format=='json':raw=json.dumps(rows).encode()
        else:
            out=io.StringIO();writer=csv.DictWriter(out,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows);raw=out.getvalue().encode()
        return ingest_ownership(raw,format,meta,slate,ingested_utc='2026-10-22T16:00:00Z'),raw
    def test_complete_probabilities_and_checksum(self):
        s,m,r=self.fixtures();p,raw=self.run_feed(s,m,r)
        self.assertTrue(p['report']['predictive_eligible']);self.assertEqual(p['raw_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(len(p['report']['candidate_exclusion_exceptions']),1)
        self.assertAlmostEqual(sum(require_calibratable(p)[0]),1)
    def test_missing_is_unknown_explicit_zero_stays_zero(self):
        s,m,r=self.fixtures();r.pop();r[0]['target_ownership_cpt']=0
        p,_=self.run_feed(s,m,r)
        self.assertIsNone(p['records'][-1]['target_ownership_cpt']);self.assertEqual(p['records'][0]['target_ownership_cpt'],0)
        with self.assertRaises(OwnershipIngestionError):require_calibratable(p)
    def test_percent_csv_conversion_preserves_raw_and_metadata(self):
        s,m,r=self.fixtures();m['unit']='percent'
        for row in r:
            row['target_ownership_cpt']*=100;row['target_ownership_flex']*=100
        original=deepcopy(r);p,raw=self.run_feed(s,m,r,'csv')
        self.assertEqual(r,original);self.assertEqual(p['metadata']['unit'],'percent')
        self.assertAlmostEqual(p['records'][0]['target_ownership_cpt'],1/6)
    def test_skewed_sums_logged_without_normalization(self):
        s,m,r=self.fixtures();r[0]['target_ownership_cpt']+=.05
        p,_=self.run_feed(s,m,r)
        self.assertAlmostEqual(p['report']['special_sum_residual'],.05)
        self.assertEqual(p['records'][0]['target_ownership_cpt'],r[0]['target_ownership_cpt'])
        self.assertFalse(p['report']['calibration_ready'])
    def test_wrong_slate_game_or_player_rejected(self):
        for kind in ['slate','game','player']:
            s,m,r=self.fixtures()
            if kind=='slate':r[0]['slate_id']='other'
            elif kind=='game':m['observed_game_set']=['A@C']
            else:r[0]['player_id']='absent'
            with self.assertRaises(OwnershipIngestionError):self.run_feed(s,m,r)
    def test_duplicate_id_and_combined_feed_rejected(self):
        s,m,r=self.fixtures();r.append(r[0].copy())
        with self.assertRaises(OwnershipIngestionError):self.run_feed(s,m,r)
        s,m,r=self.fixtures();r[0]['total']=r[0].pop('target_ownership_cpt')
        with self.assertRaises(OwnershipIngestionError):self.run_feed(s,m,r)
    def test_malformed_numbers_not_coerced_to_unknown(self):
        for value in ['oops',True,float('nan'),float('inf')]:
            s,m,r=self.fixtures();r[0]['target_ownership_flex']=value
            with self.assertRaises(OwnershipIngestionError):self.run_feed(s,m,r)
    def test_unknown_retrieval_not_filled_from_ingestion(self):
        s,m,r=self.fixtures();m['last_successful_received_utc']=None
        p,_=self.run_feed(s,m,r)
        self.assertIsNone(p['metadata']['last_successful_received_utc']);self.assertIsNone(p['report']['retrieval_age_minutes'])
        self.assertFalse(p['report']['predictive_eligible'])
    def test_actual_targets_not_classified_as_predictive(self):
        s,m,r=self.fixtures();m['target_kind']='actual';p,_=self.run_feed(s,m,r)
        with self.assertRaises(OwnershipIngestionError):require_calibratable(p)
        require_calibratable(p,predictive=False)
    def test_wrong_units_and_non_utc_rejected(self):
        s,m,r=self.fixtures();m['unit']='auto'
        with self.assertRaises(OwnershipIngestionError):self.run_feed(s,m,r)
        s,m,r=self.fixtures();m['request_started_utc']='2026-10-22T15:00:00'
        with self.assertRaises(OwnershipIngestionError):self.run_feed(s,m,r)
    def test_error_refresh_keeps_old_received_timestamp(self):
        s,m,r=self.fixtures();m['request_status']='error';m['last_successful_received_utc']='2026-10-22T14:01:00Z'
        p,_=self.run_feed(s,m,r)
        self.assertEqual(p['report']['retrieval_age_minutes'],119)
        self.assertIsNone(p['report']['provider_data_age_minutes'])

    def test_expected_checksum_mismatch_rejected(self):
        s,m,r=self.fixtures();raw=json.dumps(r).encode()
        with self.assertRaises(OwnershipIngestionError):ingest_ownership(raw,'json',m,s,expected_raw_sha256='0'*64)

    def test_future_provider_timestamp_blocks_predictive_gate(self):
        s,m,r=self.fixtures();m['provider_updated_utc']='2026-10-22T17:00:00Z'
        p,_=self.run_feed(s,m,r)
        self.assertFalse(p['report']['predictive_eligible'])
        self.assertIn('provider_updated_utc',p['report']['future_timestamp_fields'])
