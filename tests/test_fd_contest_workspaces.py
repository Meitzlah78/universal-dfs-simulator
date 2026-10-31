import unittest
import pandas as pd
from simmah_fd_contest_workspaces import activate_contest, STORE


class ContestWorkspacesTest(unittest.TestCase):
    def test_two_contests_restore_independent_results_and_settings(self):
        state = {'fd_selected_contest': 'A', 'upload': b'same slate'}
        activate_contest(state, b'template', 'Full Roster', 'A')
        state['fd_lineups_full_roster'] = pd.DataFrame({'QB': ['A quarterback']})
        state['fd_full_roster_evaluation_context'] = {'id': 'A', 'field_size': 600000}
        state['payscale_FanDuel Full Roster_choice'] = 'paid contest'
        state['portfolio_exposure_diversity_FanDuel_Full Roster_v1'] = 75
        activate_contest(state, b'template', 'Full Roster', 'B')
        self.assertNotIn('fd_lineups_full_roster', state)
        self.assertNotIn('payscale_FanDuel Full Roster_choice', state)
        state['fd_lineups_full_roster'] = pd.DataFrame({'QB': ['B quarterback']})
        state['portfolio_exposure_diversity_FanDuel_Full Roster_v1'] = 25
        activate_contest(state, b'template', 'Full Roster', 'A')
        self.assertEqual(state['fd_lineups_full_roster'].iloc[0, 0], 'A quarterback')
        self.assertEqual(state['fd_full_roster_evaluation_context']['id'], 'A')
        self.assertEqual(state['payscale_FanDuel Full Roster_choice'], 'paid contest')
        self.assertEqual(state['portfolio_exposure_diversity_FanDuel_Full Roster_v1'], 75)
        self.assertEqual(state['upload'], b'same slate')
        activate_contest(state, b'template', 'Full Roster', 'B')
        self.assertEqual(state['fd_lineups_full_roster'].iloc[0, 0], 'B quarterback')
        self.assertEqual(state['portfolio_exposure_diversity_FanDuel_Full Roster_v1'], 25)

    def test_same_contest_rerun_preserves_live_updates_and_initial_build(self):
        state = {'fd_lineups_full_roster': 'existing'}
        self.assertFalse(activate_contest(state, b'template', 'Full Roster', 'A'))
        self.assertEqual(state['fd_lineups_full_roster'], 'existing')
        state['fd_lineups_full_roster'] = 'rebuilt'
        self.assertFalse(activate_contest(state, b'template', 'Full Roster', 'A'))
        self.assertEqual(state['fd_lineups_full_roster'], 'rebuilt')

    def test_first_switch_after_upgrade_saves_old_contest_under_its_own_id(self):
        state = {'selected_fd_contest': {'id': 'A'}, 'fd_lineups_full_roster': 'A build'}
        activate_contest(state, b'template', 'Full Roster', 'B')
        self.assertNotIn('fd_lineups_full_roster', state)
        activate_contest(state, b'template', 'Full Roster', 'A')
        self.assertEqual(state['fd_lineups_full_roster'], 'A build')

    def test_player_preferences_restore_without_overwriting_new_projection(self):
        from simmah_fd_contest_workspaces import restore_player_controls
        state = {'fd_player_controls_Full Roster': pd.DataFrame([
            {'Name': 'A', 'Fade': True, 'Lock': False, 'Min Exposure %': 0, 'Max Exposure %': 20, 'Projection': 1}])}
        frame = pd.DataFrame([
            {'Name': 'A', 'Fade': False, 'Lock': False, 'Min Exposure %': 0, 'Max Exposure %': 100, 'Projection': 25},
            {'Name': 'B', 'Fade': False, 'Lock': False, 'Min Exposure %': 0, 'Max Exposure %': 100, 'Projection': 15}])
        restored = restore_player_controls(frame, state, 'Full Roster')
        self.assertTrue(restored.loc[0, 'Fade'])
        self.assertEqual(restored.loc[0, 'Max Exposure %'], 20)
        self.assertEqual(restored.loc[0, 'Projection'], 25)
        self.assertEqual(restored.loc[1, 'Max Exposure %'], 100)

    def test_changed_upload_or_format_cannot_inherit_another_build(self):
        state = {}
        activate_contest(state, b'first template', 'Full Roster', 'A')
        state['fd_lineups_full_roster'] = 'original'
        activate_contest(state, b'second template', 'Full Roster', 'A')
        self.assertNotIn('fd_lineups_full_roster', state)
        activate_contest(state, b'first template', 'Single Game', 'A')
        self.assertNotIn('fd_lineups_full_roster', state)
        activate_contest(state, b'first template', 'Full Roster', 'A')
        self.assertEqual(state['fd_lineups_full_roster'], 'original')

    def test_action_upload_and_readonly_widget_values_are_never_restored(self):
        state = {'_slate_action_keys': {'fd_full_roster_build'},
                 '_slate_readonly_keys': {'fd_player_pool_editor_full_roster'}}
        activate_contest(state, b'template', 'Full Roster', 'A')
        state.update(fd_full_roster_build=True, fd_player_pool_editor_full_roster={'edited_rows': {}},
                     saved_contest_choice_FanDuel_backup=True)
        state['saved_contest_choice_FanDuel Full Roster_backup'] = True
        activate_contest(state, b'template', 'Full Roster', 'B')
        activate_contest(state, b'template', 'Full Roster', 'A')
        self.assertNotIn('fd_full_roster_build', state)
        self.assertNotIn('fd_player_pool_editor_full_roster', state)
        self.assertNotIn('saved_contest_choice_FanDuel Full Roster_backup', state)

    def test_saved_builds_survive_workspace_serialization(self):
        from simmah_slate_workspaces import encode, decode
        state = {}
        activate_contest(state, b'template', 'Full Roster', 'A')
        state['fd_saved_builds'] = {'pool': {'lineups': pd.DataFrame({'QB': ['Player A']})}}
        activate_contest(state, b'template', 'Full Roster', 'B')
        restored = decode(encode(state))
        activate_contest(restored, b'template', 'Full Roster', 'A')
        self.assertEqual(restored['fd_saved_builds']['pool']['lineups'].iloc[0, 0], 'Player A')


if __name__ == '__main__':
    unittest.main()
