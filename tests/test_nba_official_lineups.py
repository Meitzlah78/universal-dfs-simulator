import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import pandas as pd
from simmah_nba_official_lineups import parse_daily_lineups
from simmah_nba_confirmed import current_confirmed_pool


class OfficialLineupTests(unittest.TestCase):
    def payload(self,status='Confirmed'):
        def team(abbr,tid):
            players=[{'personId':tid*10+i,'teamId':tid,'playerName':abbr+' Player '+str(i),
                'position':pos,'lineupStatus':status,'rosterStatus':'Active',
                'timestamp':'2026-10-28T18:30:00'} for i,pos in enumerate(('PG','SG','SF','PF','C'))]
            players += [{**p,'position':'','lineupStatus':'Confirmed'} for p in players]
            players += [{'personId':999,'teamId':tid,'playerName':'Bench','position':'',
                'lineupStatus':'Confirmed','rosterStatus':'Active','timestamp':'2026-10-28T18:30:00'}]
            return {'teamId':tid,'teamAbbreviation':abbr,'players':players}
        return {'games':[{'homeTeam':team('NYK',1),'awayTeam':team('PHI',2)}]}

    def test_confirmed_only_positioned_five_not_roster_confirmation(self):
        values=parse_daily_lineups(self.payload(),'2026-10-28',[('NY','PHI')])
        self.assertEqual(len(values),10)
        self.assertTrue(all(v['Starter Confirmed'] for v in values.values()))
        self.assertFalse(any(k[0]=='bench' for k in values))

    def test_expected_stays_expected_despite_confirmed_bench_rows(self):
        values=parse_daily_lineups(self.payload('Expected'),'2026-10-28',[('NY','PHI')])
        self.assertFalse(any(v['Starter Confirmed'] for v in values.values()))

    def test_wrong_day_and_matchup_rejected(self):
        for day,pairs in [('2026-10-29',[('NY','PHI')]),('2026-10-28',[('NY','MIL')])]:
            with self.assertRaises(ValueError):parse_daily_lineups(self.payload(),day,pairs)

    def test_partial_duplicate_or_inactive_five_is_not_confirmed(self):
        for change in ('position','personId','rosterStatus'):
            data=self.payload()
            row=data['games'][0]['homeTeam']['players'][0]
            row[change]={'position':'','personId':11,'rosterStatus':'Inactive'}[change]
            values=parse_daily_lineups(data,'2026-10-28',[('NY','PHI')])
            self.assertTrue(all(k[1]=='PHI' for k in values))

    def test_fresh_official_fallback_updates_only_starter_flags(self):
        values=parse_daily_lineups(self.payload(),'2026-10-28',[('NY','PHI')])
        p=pd.DataFrame([{'Name':name,'Team':team,'Opponent':'PHI' if team=='NY' else 'NY',
            'Projection':30.,'Projected Minutes':32.,'Salary':6000} for name,team in values])
        with patch('simmah_nba_confirmed.cached_confirmed_status',side_effect=TimeoutError()), \
             patch('simmah_nba_confirmed.cached_player_lineups',side_effect=OSError('403')), \
             patch('simmah_nba_official_lineups.cached_lineups',return_value={
                 'players':values,'checked_at':200,'source':'NBA.com daily lineups'}):
            view,status=current_confirmed_pool(SimpleNamespace(session_state={}),p,'2026-10-28',[('NY','PHI')])
        self.assertFalse(status['stale'])
        self.assertEqual(status['issue'],'')
        self.assertTrue(view['Starter Confirmed'].all())
        for column in ('Projection','Projected Minutes','Salary'):
            pd.testing.assert_series_equal(p[column],view[column])

    def test_outage_keeps_last_good_but_marks_it_stale(self):
        values=parse_daily_lineups(self.payload(),'2026-10-28',[('NY','PHI')])
        p=pd.DataFrame([{'Name':name,'Team':team,'Expected Starter':True,
            'Starter Confirmed':False} for name,team in values])
        app=SimpleNamespace(session_state={'nba_confirmed_last_good':{
            'scope':('2026-10-28',(('NY','PHI'),)),
            'response':{'players':values,'checked_at':100}}})
        with patch('simmah_nba_confirmed.cached_confirmed_status',side_effect=TimeoutError()), \
             patch('simmah_nba_confirmed.cached_player_lineups',side_effect=OSError('403')), \
             patch('simmah_nba_official_lineups.cached_lineups',side_effect=OSError('timeout')):
            view,status=current_confirmed_pool(app,p,'2026-10-28',[('NY','PHI')])
        self.assertTrue(status['stale'])
        self.assertTrue(view['Lineup Status Stale'].all())
