import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from pathlib import Path
import pandas as pd
from simmah_nfl_game_exclusions import game_options, excluded_player_names, render_game_exclusions


class GameExclusionsTest(unittest.TestCase):
    def pool(self):
        return pd.DataFrame([
            {'Name': 'Detroit player', 'Team': 'DET', 'Opponent': 'GB', 'Game': 'GB@DET'},
            {'Name': 'Green Bay player', 'Team': 'GB', 'Opponent': 'DET', 'Game': 'GB@DET'},
            {'Name': 'Atlanta player', 'Team': 'ATL', 'Opponent': 'SF', 'Game': 'SF@ATL'},
            {'Name': 'San Francisco player', 'Team': 'SF', 'Opponent': 'ATL', 'Game': 'SF@ATL'}])

    def test_exclusion_removes_both_teams_without_mutating_full_pool(self):
        pool = self.pool(); original = pool.copy(deep=True)
        names = excluded_player_names(pool, ['GB @ DET'])
        self.assertEqual(names, {'Detroit player', 'Green Bay player'})
        self.assertEqual(pool.loc[~pool.Name.isin(names), 'Name'].tolist(), ['Atlanta player', 'San Francisco player'])
        pd.testing.assert_frame_equal(pool, original)
        self.assertEqual(len(game_options(pool)), 2)

    def test_aliases_and_missing_game_text_use_verified_team_pairs(self):
        pool = pd.DataFrame([{'Name': 'A', 'Team': 'WSH', 'Opponent': 'JAC'},
                             {'Name': 'B', 'Team': 'JAX', 'Opponent': 'WAS'}])
        self.assertEqual(excluded_player_names(pool, list(game_options(pool))), {'A', 'B'})
        self.assertEqual(len(game_options(pool)), 1)

    def test_none_and_all_exclusions(self):
        pool = self.pool()
        self.assertEqual(excluded_player_names(pool, []), set())
        self.assertEqual(excluded_player_names(pool, list(game_options(pool))), set(pool.Name))

    def test_changed_slate_prunes_unavailable_widget_selections_before_render(self):
        key = 'nfl_excluded_games_FanDuel_Full_Roster'
        state = {key: ['GB @ DET', 'OLD @ GAME']}
        def choose(label, options, **kwargs):
            self.assertEqual(state[key], ['GB @ DET'])
            return state[key]
        st = SimpleNamespace(session_state=state, multiselect=choose, caption=Mock())
        self.assertEqual(render_game_exclusions(st, self.pool(), 'FanDuel', 'Full Roster'),
                         {'Detroit player', 'Green Bay player'})

    def test_saved_candidates_and_manual_editors_use_filtered_user_pools(self):
        source = Path('dfs_app.py').read_text()
        self.assertIn('pool = fd_user_pool.drop_duplicates', source)
        self.assertIn('_fd_eligible_now = set(fd_user_pool', source)
        self.assertIn('render_editor(st, _fd_diverse_portfolio, fd_user_pool', source)
        self.assertIn('classic_portfolio_source[_classic_slots].isin(set(classic_pool', source)
        self.assertIn('pool = players_df.copy()\n                        pool["Eligible"]', source)
        self.assertIn('fd_pool = fd_players.copy()', source)


if __name__ == '__main__':
    unittest.main()
