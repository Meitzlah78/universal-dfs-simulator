"""Scoring fixtures and shared NFL event accounting, without Streamlit/network."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
import numpy as np
import pandas as pd
from simmah_nfl_engine import simulate_stat_lines


def app_functions():
    tree = ast.parse(Path('dfs_app.py').read_text())
    wanted = {'DFS_SCORING_RULES', 'score_nfl_stat_line', 'simulate_fd_play_by_play',
              '_historical_player_average', '_normalize_historical_player_names',
              '_build_historical_name_index', 'normalize_projection_player_name', 'fit_projection_event_inputs_cached'}
    nodes = [x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name in wanted
             or isinstance(x, ast.Assign) and any(isinstance(t, ast.Name) and t.id in wanted for t in x.targets)]
    for node in nodes:
        if isinstance(node,ast.FunctionDef):node.decorator_list=[]
    progress = SimpleNamespace(progress=lambda *a, **kw: None)
    ns = {'np': np, 'pd': pd, 'SIMULATION_COUNT': 10000,
          'st': SimpleNamespace(progress=lambda *a, **kw: progress, caption=lambda *a, **kw: None, session_state={}),
          'load_nfl_historical_player_stats': lambda: pd.DataFrame()}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'dfs_app.py', 'exec'), ns)
    return ns


def fixture():
    rows, roles = [], {}
    for team, opp in [('A', 'B'), ('B', 'A')]:
        for pos, proj in [('QB',20), ('RB',15), ('WR',18), ('TE',10), ('K',8), ('DST',6)]:
            rows.append(dict(Name=team+pos, Team=team, Opponent=opp, Position=pos, Projection=proj))
        roles[team+'QB'] = dict(pass_attempts=34, completions=22, interceptions=.7, carries=4, rush_yards=20)
        roles[team+'RB'] = dict(carries=20, rush_yards=85, targets=4, receptions=3, rec_yards=22)
        roles[team+'WR'] = dict(targets=9, receptions=6, rec_yards=80)
        roles[team+'TE'] = dict(targets=6, receptions=4, rec_yards=45)
    return pd.DataFrame(rows), roles


class NFLGameTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pool, cls.roles = fixture()
        cls.stats, cls.games = simulate_stat_lines(cls.pool, cls.roles, np.random.default_rng(42), 10000, return_diagnostics=True)
        cls.app = app_functions()

    def test_exact_site_scoring(self):
        line = dict(passing_yards=300, passing_tds=2, interceptions=1, rushing_yards=100,
                    rushing_tds=1, receiving_yards=100, receiving_tds=1, receptions=5,
                    fumbles_lost=1, two_point_conversions=3)
        score = self.app['score_nfl_stat_line']
        self.assertEqual(score(line, 'DraftKings'), 70)
        self.assertEqual(score(line, 'FanDuel'), 57.5)
        self.assertEqual(score(dict(fg_under_40=1, fg_40_49=1, fg_50_plus=1, extra_points_made=2), 'DraftKings'), 14)
        for site in ('DraftKings', 'FanDuel'):
            for pa, expected in [(0,10),(6,7),(13,4),(20,1),(27,0),(34,-1),(35,-4)]:
                for yards in (50,550):
                    self.assertEqual(score(dict(is_defense=1, points_allowed=pa, yards_allowed=yards),site), expected)
            self.assertLess(score(dict(interceptions=2), site), 0)

    def test_pass_and_turnover_conservation(self):
        for team, opp in [('A','B'),('B','A')]:
            qb = self.stats[team+'QB']
            for pass_key, rec_key in [('passing_yards','receiving_yards'),('passing_tds','receiving_tds')]:
                np.testing.assert_allclose(qb[pass_key], sum(self.stats[team+p][rec_key] for p in ('RB','WR','TE')), atol=.001)
            np.testing.assert_array_equal(qb['interceptions'], self.stats[opp+'DST']['def_interceptions'])
            np.testing.assert_array_equal(sum(self.stats[team+p]['fumbles_lost'] for p in ('QB','RB','WR','TE')), self.stats[opp+'DST']['fumble_recoveries'])

    def test_scoreboard_and_one_conversion_per_td(self):
        for team, other in [('A','B'),('B','A')]:
            g = self.games[team]
            expected = 6*(g['offensive_tds']+g['defensive_tds'])+2*g['safeties']+3*g['fg_made']+g['pat_made']+2*g['two_made']
            np.testing.assert_array_equal(g['points'], expected)
            np.testing.assert_array_equal(g['pat_attempts']+g['two_attempts'], g['offensive_tds']+g['defensive_tds'])
            np.testing.assert_array_equal(self.stats[other+'DST']['points_allowed'], g['chargeable'])
            np.testing.assert_array_equal(g['chargeable'], g['points']-6*g['defensive_tds']-2*g['safeties'])
            np.testing.assert_array_equal(g['pat_made'], self.stats[team+'K']['extra_points_made'])
            self.assertTrue((g['clock_remaining'] <= 0).all())

    def test_missed_kicks_and_two_point_plays_exist(self):
        for team in ('A','B'):
            g = self.games[team]
            self.assertGreater((g['fg_attempts']-g['fg_made']).sum(), 0)
            self.assertGreater((g['pat_attempts']-g['pat_made']).sum(), 0)
            self.assertGreater(g['two_made'].sum(), 0)
            # A passing conversion credits both passer and receiver, a rushing
            # conversion only its runner, and neither adds ordinary yards/TDs.
            credits = sum(self.stats[team+p]['two_point_conversions'] for p in ('QB','RB','WR','TE'))
            self.assertTrue((credits >= g['two_made']).all())
            self.assertTrue((credits <= 2*g['two_made']).all())

    def test_ten_thousand_independent_finite_outcomes(self):
        for site in ('DraftKings','FanDuel'):
            values = {name:self.app['score_nfl_stat_line'](dict(line,is_defense=int(name.endswith('DST'))),site) for name,line in self.stats.items()}
            frame = pd.DataFrame(values)
            self.assertEqual(frame.shape, (10000,12))
            self.assertEqual(len(frame.drop_duplicates()), 10000)
            self.assertTrue(np.isfinite(frame.to_numpy()).all())
            self.assertTrue((frame[['ADST','BDST']].to_numpy() < 0).any())

    def test_all_formats_use_shared_unscaled_stat_scoring(self):
        for site in ('DraftKings','FanDuel'):
            result = self.app['simulate_fd_play_by_play'](self.pool,np.random.default_rng(7),1000,platform=site)
            params,_ = self.app['fit_projection_event_inputs_cached'](self.pool,{},site,'test')
            raw = simulate_stat_lines(self.pool,{},np.random.default_rng(7),1000,projection_inputs=params,scoring_platform=site)
            for name,line in raw.items():
                expected = self.app['score_nfl_stat_line'](dict(line,is_defense=int(name.endswith('DST'))),site)
                np.testing.assert_array_equal(result[name], expected)
            self.assertEqual(result.attrs['independent_outcomes'],1000)
        source = Path('dfs_app.py').read_text()
        tree = ast.parse(source)
        run = next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='run_game_simulations')
        calls = [n.func.id for n in ast.walk(run) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)]
        self.assertIn('simulate_fd_play_by_play',calls)
        self.assertNotIn('_simulate_scored_player_outcomes',calls)

    def test_historical_two_points_and_all_fumbles(self):
        history = pd.DataFrame([dict(player_display_name='Test Player',week=1,season=2026,position='QB',
            passing_2pt_conversions=1,rushing_2pt_conversions=1,receiving_2pt_conversions=1,
            sack_fumbles_lost=1,rushing_fumbles_lost=1,receiving_fumbles_lost=1)])
        points = self.app['_historical_player_average']('Test Player','QB','FanDuel',history,return_scores=True)
        self.assertIsNotNone(points)
        # 3 conversions (6 points) minus 3 lost fumbles (6 points).
        # Inspect the returned historical-score array below.
        self.assertEqual(float(points[0][0]), 0)
        for col in ('sack_fumbles_lost','rushing_fumbles_lost','receiving_fumbles_lost'):
            history[col] = 0
        points = self.app['_historical_player_average']('Test Player','QB','FanDuel',history,return_scores=True)
        self.assertEqual(float(points[0][0]), 6)

    def test_historical_roles_match_names_with_spaces(self):
        from unittest.mock import patch
        ns = app_functions()
        pool = self.pool.copy()
        pool.loc[pool['Name']=='AQB', 'Name'] = 'Alpha Quarterback'
        history = pd.DataFrame([dict(player_display_name='Alpha Quarterback', week=1,
            season=2026, attempts=34, completions=22, carries=4, rushing_yards=20)])
        ns['load_nfl_historical_player_stats'] = lambda: history
        with patch('simmah_nfl_engine.simulate_stat_lines', wraps=simulate_stat_lines) as engine:
            ns['simulate_fd_play_by_play'](pool,np.random.default_rng(7),n=50)
            roles = engine.call_args.args[1]
            self.assertEqual(roles['Alpha Quarterback']['pass_attempts'],34)
            self.assertEqual(roles['Alpha Quarterback']['carries'],4)

    def test_team_aliases_and_missing_players(self):
        alias_pool = self.pool.copy()
        alias_pool['Team'] = alias_pool['Team'].map({'A':'JAC','B':'WSH'})
        alias_pool['Opponent'] = alias_pool['Opponent'].map({'A':'JAX','B':'WAS'})
        raw, games = simulate_stat_lines(alias_pool,self.roles,np.random.default_rng(9),500,return_diagnostics=True)
        self.assertEqual(set(games), {'JAX','WAS'})
        self.assertGreater(games['JAX']['points'].sum(),0)
        # A filtered-out QB must not stop the remaining receivers from playing.
        without_qb = self.pool[self.pool['Position'] != 'QB']
        raw = simulate_stat_lines(without_qb,self.roles,np.random.default_rng(9),500)
        self.assertGreater(raw['AWR']['receptions'].sum(),0)
        lone_defense = self.pool[self.pool['Name']=='ADST']
        raw = simulate_stat_lines(lone_defense,{},np.random.default_rng(9),500)
        self.assertGreater(raw['ADST']['points_allowed'].mean(),0)


if __name__ == '__main__':
    unittest.main()
