import io,json,unittest
from urllib.error import HTTPError
from simmah_fantasypros import check_weekly_access

class FantasyProsTests(unittest.TestCase):
    def test_header_and_week_and_safe_metadata(self):
        def opener(request,timeout):
            self.assertEqual(request.get_header('X-api-key'),'private-test-key')
            self.assertIn('week=6',request.full_url)
            return io.StringIO(json.dumps({'season':2026,'week':6,'players':[{'name':'QB','stats':[{'points':20,'pass_yds':250,'unknown':'private-test-key'}]}]}))
        result=check_weekly_access('private-test-key',2026,6,opener)
        self.assertTrue(result['ok']);self.assertEqual(result['qb_players'],1)
        self.assertNotIn('private-test-key',json.dumps(result));self.assertNotIn('unknown',result['scoring_fields'])
    def test_rejected_key_never_leaks_response(self):
        def opener(request,timeout):raise HTTPError(request.full_url,403,'private-test-key',{},None)
        result=check_weekly_access('private-test-key',2026,6,opener)
        self.assertFalse(result['ok']);self.assertIn('403',result['status'])
        self.assertNotIn('private-test-key',str(result))
    def test_wrong_week_and_missing_key_rejected(self):
        opener=lambda *a,**k:io.StringIO('{"season":2026,"week":7,"players":[{}]}')
        self.assertFalse(check_weekly_access('test',2026,6,opener)['ok'])
        self.assertFalse(check_weekly_access('',2026,6,opener)['ok'])

class CoverageTests(unittest.TestCase):
    def test_all_positions_are_requested_and_numeric_stats_exported(self):
        from simmah_fantasypros import check_all_positions
        from urllib.parse import urlparse,parse_qs
        seen=[]
        def opener(request,timeout):
            pos=parse_qs(urlparse(request.full_url).query)['position'][0];seen.append(pos)
            return io.StringIO(json.dumps({'season':2026,'week':6,'players':[
                {'name':'Player','team_id':'SF','position_id':pos,'stats':[{'rec_rec':'5.5','points':None,'private':'secret'}]}]}))
        result=check_all_positions('secret',2026,6,opener)
        self.assertEqual(seen,['QB','RB','WR','TE','K','DST'])
        self.assertEqual(result['positions'][1]['players'][0]['stats'],[{'rec_rec':5.5}])
        self.assertNotIn('secret',json.dumps(result))
    def test_rate_limit_stops_remaining_requests(self):
        from simmah_fantasypros import check_all_positions
        calls=[]
        def opener(request,timeout):
            calls.append(request.full_url)
            raise HTTPError(request.full_url,429,'secret',{},None)
        result=check_all_positions('secret',2026,6,opener)
        self.assertEqual(len(calls),1);self.assertEqual(len(result['positions']),1)

if __name__=='__main__':unittest.main()
