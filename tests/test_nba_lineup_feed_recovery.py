"""Regression coverage for degraded NBA lineup sources."""
import io,json,unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from simmah_nba_confirmed import download_lineup_page,current_confirmed_pool

class LineupRecoveryTests(unittest.TestCase):
    def test_timeout_retries_once_and_closes_success_response(self):
        body=io.BytesIO(b'page')
        with patch('simmah_nba_confirmed.urlopen',side_effect=[TimeoutError('read'),body]) as fetch:
            self.assertEqual(download_lineup_page('2026-10-28')['html'],'page')
            self.assertEqual(fetch.call_count,2)
        self.assertTrue(body.closed)

    def test_persistent_timeout_is_bounded_and_403_is_not_retried(self):
        with patch('simmah_nba_confirmed.urlopen',side_effect=TimeoutError('read')) as fetch:
            with self.assertRaises(TimeoutError):download_lineup_page('2026-10-28')
            self.assertEqual(fetch.call_count,2)
        with patch('simmah_nba_confirmed.urlopen',side_effect=HTTPError('url',403,'Forbidden',{},None)) as fetch:
            with self.assertRaises(HTTPError):download_lineup_page('2026-10-28')
            self.assertEqual(fetch.call_count,1)

    def test_player_request_has_standard_json_headers(self):
        from simmah_nba_lineups import download_lineup_status
        body=io.BytesIO(json.dumps([{'firstName':'A','lastName':'B','team':{'abbr':'NY'},
            'opponent':{'team':'PHI'},'game':{'dateTime':'2026-10-28 19:00:00'},
            'lineup':{'slot':True,'isConfirmed':False}}]).encode())
        with patch('simmah_nba_lineups.urlopen',return_value=body) as fetch:
            download_lineup_status('123','2026-10-28',[('NY','PHI')])
            request=fetch.call_args.args[0]
            self.assertEqual(request.get_header('Accept'),'application/json')
            self.assertTrue(request.get_header('User-agent'))
        self.assertTrue(body.closed)

    def test_stale_primary_can_use_fresh_fallback_and_preserves_scores(self):
        import pandas as pd
        p=pd.DataFrame([{'Name':'Player '+str(i),'Team':'NY','Opponent':'PHI',
            'Projection':30.,'Expected Starter':True,'Starter Confirmed':False} for i in range(5)])
        values={(r.Name.casefold(),r.Team):{'Expected Starter':True,'Starter Confirmed':True} for r in p.itertuples()}
        app=SimpleNamespace(session_state={})
        with patch('simmah_nba_confirmed.cached_confirmed_status',return_value={'players':values,'checked_at':100,'stale':True,'issue':'timeout'}), \
             patch('simmah_nba_confirmed.cached_player_lineups',return_value={'players':values,'checked_at':200}):
            view,status=current_confirmed_pool(app,p,'2026-10-28',[('NY','PHI')])
        self.assertFalse(status['stale'])
        self.assertEqual(status['issue'],'')
        self.assertTrue(view['Starter Confirmed'].all())
        self.assertTrue(view.Projection.eq(30).all())
        # A later outage must not replace this saved response with the older page.
        with patch('simmah_nba_confirmed.cached_confirmed_status',return_value={'players':{},'checked_at':100,'stale':True}), \
             patch('simmah_nba_confirmed.cached_player_lineups',side_effect=OSError('403')):
            view,status=current_confirmed_pool(app,p,'2026-10-28',[('NY','PHI')])
        self.assertTrue(status['stale'])
        self.assertEqual(status['checked_at'],200)
        self.assertTrue(view['Lineup Status Stale'].all())
