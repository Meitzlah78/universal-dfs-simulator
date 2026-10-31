import ast
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import unittest
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from simmah_weather import (parse_wind_mph,kickoff_hints,schedule_games,select_game,
                            venue_location,forecast_for_game,weather_factors,resolve_game)
from simmah_nfl_engine import simulate_stat_lines


def schedule():
    return {'events':[{'id':'1','date':'2026-10-19T00:20:00Z','competitions':[{
        'competitors':[{'homeAway':'home','team':{'abbreviation':'GB'}},
                       {'homeAway':'away','team':{'abbreviation':'DAL'}}],
        'venue':{'id':'3798','fullName':'Lambeau Field','indoor':False}}]}]}


def periods(kickoff):
    start=kickoff.replace(minute=0)
    return [{'startTime':(start+timedelta(hours=i)).isoformat(),
             'endTime':(start+timedelta(hours=i+1)).isoformat(),
             'windSpeed':'15 to 20 mph','shortForecast':'Rain',
             'probabilityOfPrecipitation':{'value':70}} for i in range(5)]


class WeatherTest(unittest.TestCase):
    def test_schedule_fallback_verifies_game_without_guessing_venue(self):
        now=datetime(2026,10,18,12,tzinfo=timezone.utc)
        hint=now
        calls=[]
        def fetch(url):
            calls.append(url)
            if 'scoreboard' in url:
                raise OSError('range/daily feed unavailable')
            return schedule()
        game=resolve_game([], 'DAL', 'GB', now, hint, fetch)
        self.assertEqual(game['venue']['fullName'],'Lambeau Field')
        self.assertEqual(len(calls),2)
        self.assertIn('/teams/dal/schedule?',calls[-1])
        self.assertIsNone(resolve_game([], 'CAR', 'GB', now, hint, fetch))
        self.assertIsNone(resolve_game([], 'DAL', 'GB', now, hint,
            lambda url: {'events':[]}))

    def test_wind_parser(self):
        self.assertEqual(parse_wind_mph('15 to 20 mph'),20)
        self.assertEqual(parse_wind_mph('7.5 mph'),7.5)
        self.assertEqual(parse_wind_mph('Calm'),0)
        self.assertIsNone(parse_wind_mph(None))
        self.assertAlmostEqual(parse_wind_mph({'value':10,'unitCode':'wmoUnit:m_s-1'}),22.3694)

    def test_kickoff_and_away_venue(self):
        hints=kickoff_hints([{'Game Info':'DAL@GB 10/18/2026 08:20PM ET'}])
        games=schedule_games(schedule())
        game=select_game(games,'DAL','GB',datetime(2026,10,17,tzinfo=timezone.utc),hints[('DAL','GB')])
        self.assertEqual(game['home'],'GB')
        self.assertEqual(game['kickoff'].hour,0)  # correct next-day UTC kickoff
        self.assertEqual(venue_location(game['venue']), (44.5013,-88.0622,False))
        self.assertIsNone(select_game(games+games,'DAL','GB',datetime(2026,10,17,tzinfo=timezone.utc)))

    def test_neutral_and_indoor_venues(self):
        self.assertIsNone(venue_location({'id':'2455','fullName':'Wembley Stadium','indoor':False}))
        self.assertEqual(venue_location({'id':'6501','fullName':'Allegiant Stadium','indoor':True}), (None,None,True))
        self.assertEqual(venue_location({'id':'7065','fullName':'SoFi Stadium','indoor':False})[2],True)

    def test_only_game_hours_and_complete_coverage(self):
        kickoff=datetime(2026,10,19,0,20,tzinfo=timezone.utc)
        rows=periods(kickoff)
        storm=dict(rows[0],startTime='2026-10-22T00:00:00Z',endTime='2026-10-22T01:00:00Z',windSpeed='80 mph',shortForecast='Blizzard')
        wx=forecast_for_game(rows+[storm],kickoff)
        self.assertEqual(wx['status'],'Available')
        self.assertEqual(wx['wind_mph'],20)
        self.assertFalse(wx['heavy_snow'])
        self.assertTrue(forecast_for_game(rows[:1],kickoff)['status'].startswith('Unavailable'))
        self.assertTrue(forecast_for_game([storm],kickoff)['status'].startswith('Unavailable'))
        self.assertTrue(forecast_for_game(rows[:2]+rows[3:],kickoff)['status'].startswith('Unavailable'))

    def test_neutral_missing_weather_and_impacts(self):
        neutral=weather_factors({})
        self.assertEqual(weather_factors({'status':'Unavailable','wind_mph':40}),neutral)
        self.assertEqual(weather_factors({'status':'Available','indoor':True,'wind_mph':40}),neutral)
        bad=weather_factors({'status':'Available','wind_mph':25,'precip_pct':80,'heavy_snow':True})
        self.assertLess(bad['completion'],1)
        self.assertLess(bad['kick_accuracy'],1)
        self.assertGreater(bad['rush_share'],0)

    def test_app_annotation_preserves_projections_and_shares_context(self):
        source=Path('dfs_app.py').read_text()
        fn=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='apply_game_weather_context')
        kickoff=datetime(2026,10,19,0,20,tzinfo=timezone.utc)
        calls=[]
        def fetch(url):
            calls.append(url)
            if 'scoreboard' in url:return schedule()
            if '/points/' in url:return {'properties':{'forecastHourly':'https://api.weather.gov/gridpoints/test/forecast/hourly'}}
            return {'properties':{'periods':periods(kickoff)}}
        from simmah_injury_display import injury_frame
        ns={'pd':pd,'np':np,'ZoneInfo':ZoneInfo,'ThreadPoolExecutor':ThreadPoolExecutor, 'injury_frame':injury_frame,
            'fetch_game_weather_json':fetch,'st':SimpleNamespace(session_state={},expander=lambda *a,**k:nullcontext(),dataframe=Mock(),caption=Mock())}
        opponent_fn=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='build_opponent_map')
        exec(compile(ast.Module(body=[opponent_fn,fn],type_ignores=[]),'dfs_app.py','exec'),ns)
        frame=pd.DataFrame({'Name':['Dak','Love'],'Team':['DAL','GB'],'Opponent':['GB','DAL'],'Projection':[20.,21.]})
        raw=pd.DataFrame({'Game Info':['DAL@GB 10/18/2026 08:20PM ET']})
        annotated=ns['apply_game_weather_context'](frame,raw)
        pd.testing.assert_series_equal(frame['Projection'],annotated['Projection'])
        self.assertEqual(annotated['Weather Venue'].tolist(),['Lambeau Field']*2)
        self.assertEqual(annotated['Wind MPH'].tolist(),[20.]*2)
        # DK has no Opponent column yet at this call site; FD may have blanks.
        for missing in (frame.drop(columns="Opponent"), frame.assign(Opponent="—")):
            recovered=ns['apply_game_weather_context'](missing,raw)
            self.assertEqual(recovered['Opponent'].tolist(),['GB','DAL'])
            self.assertEqual(recovered['Weather Status'].tolist(),['Available']*2)
            self.assertEqual(recovered['Weather Venue'].tolist(),['Lambeau Field']*2)
            pd.testing.assert_series_equal(frame['Projection'],recovered['Projection'])
        # FD single-game uploads can omit Game Info entirely.
        recovered=ns['apply_game_weather_context'](frame.drop(columns="Opponent"),pd.DataFrame())
        self.assertEqual(recovered['Opponent'].tolist(),['GB','DAL'])
        self.assertEqual(sum('/points/' in url for url in calls),3)
        self.assertIn('44.5013,-88.0622',next(url for url in calls if '/points/' in url))

    def test_weather_changes_engine_events_with_neutral_fallback(self):
        from test_nfl_engine import fixture
        pool,roles=fixture()
        seed=42
        neutral=simulate_stat_lines(pool,roles,np.random.default_rng(seed),2000)
        unavailable=simulate_stat_lines(pool,roles,np.random.default_rng(seed),2000,
            weather_by_team={'A':{'status':'Unavailable','wind_mph':50}})
        for name in neutral:
            for key in neutral[name]:np.testing.assert_array_equal(neutral[name][key],unavailable[name][key])
        windy=simulate_stat_lines(pool,roles,np.random.default_rng(seed),2000,
            weather_by_team={'A':{'status':'Available','wind_mph':30,'precip_pct':80}})
        self.assertLess(windy['AQB']['passing_yards'].mean(),neutral['AQB']['passing_yards'].mean())
        self.assertLess(windy['BQB']['passing_yards'].mean(),neutral['BQB']['passing_yards'].mean())


if __name__=='__main__':unittest.main()
