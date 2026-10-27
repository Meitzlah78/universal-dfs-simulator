import importlib.util
from pathlib import Path
import unittest

@unittest.skipUnless(importlib.util.find_spec('streamlit'),'Streamlit not installed')
class NBAWorkspaceTests(unittest.TestCase):
    def test_missing_minutes_are_all_reported_before_build(self):
        from streamlit.testing.v1 import AppTest
        at=AppTest.from_file(str(Path(__file__).with_name('nba_ui_fixture.py')))
        at.session_state['fixture_missing_minutes']=True
        at.run(timeout=20)
        self.assertFalse(at.exception)
        self.assertTrue(at.button(key='nba_build').disabled)
        errors=' '.join(x.value for x in at.error)
        self.assertIn('Player 0',errors);self.assertIn('Player 1',errors)
        self.assertEqual(at.session_state['test_build_calls'],0)
        self.assertTrue(any(button.proto.label=='DOWNLOAD SETUP DIAGNOSTIC PACKAGE' for button in at.get('download_button')))
        self.assertIn('nba_setup_diagnostic',at.session_state)

    def test_failed_export_never_replaces_previous_build(self):
        from streamlit.testing.v1 import AppTest
        at=AppTest.from_file(str(Path(__file__).with_name('nba_ui_fixture.py'))).run(timeout=20)
        at.button(key='nba_build').click().run(timeout=20)
        self.assertFalse(at.exception)
        previous=at.session_state['nba_build_result']
        previous['regression_sentinel']='preserve'
        at.session_state['fixture_reject_export']=True
        at.button(key='nba_build').click().run(timeout=20)
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['nba_build_result']['regression_sentinel'],'preserve')
        self.assertTrue(any('Fixture export validation failed' in x.value for x in at.error))
        self.assertFalse(any('NBA build complete' in x.value for x in at.success))

    def test_build_diversity_and_legal_stale_export_without_rebuilding(self):
        from streamlit.testing.v1 import AppTest
        at=AppTest.from_file(str(Path(__file__).with_name('nba_ui_fixture.py'))).run(timeout=20)
        self.assertFalse(at.exception)
        html=' '.join(x.value for x in at.markdown)
        self.assertIn('simmah-game-strip',html)
        self.assertIn('7:00 PM ET',html)
        self.assertIn('9:30 PM ET',html)
        self.assertIn('○ Expected',html)
        at.button(key='test_source_change').click().run(timeout=20)
        self.assertTrue(at.session_state['nba_lineup_updates_found'])
        html=' '.join(x.value for x in at.markdown)
        self.assertIn('● Confirmed',html)
        self.assertIn('#d62828',html)
        at.button(key='test_refresh').click().run(timeout=20)
        self.assertFalse(at.session_state['nba_lineup_updates_found'])
        self.assertEqual(at.session_state['test_build_calls'],0)
        at.button(key='nba_build').click().run(timeout=20)
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['test_build_calls'],1)
        self.assertEqual(len(at.session_state['nba_build_result']['result']['portfolio']),5)
        self.assertIn('diagnostic_package',at.session_state['nba_build_result']['result'])
        self.assertTrue(any(button.proto.label=='DOWNLOAD CALIBRATION & SOLVER PACKAGE' for button in at.get('download_button')))
        self.assertFalse(any('capture failed' in item.value for item in at.warning))
        at.slider(key='nba_exposure_diversity').set_value(100).run(timeout=20)
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['test_build_calls'],1)
        at.slider(key='nba_build_correlation').set_value(100).run(timeout=20)
        self.assertEqual(at.session_state['test_build_calls'],1)
        self.assertFalse(at.exception)
        at.number_input(key='nba_min_salary').set_value(500).run(timeout=20)
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['test_build_calls'],1)
        exports=[x for x in at.get('download_button') if x.proto.id.endswith('-nba_entries_download')]
        self.assertEqual(len(exports),1)
        self.assertFalse(exports[0].proto.disabled)

    def test_dk_legal_stale_export_and_current_out_and_salary_guards(self):
        from streamlit.testing.v1 import AppTest
        at=AppTest.from_file(str(Path(__file__).with_name('nba_ui_fixture.py')))
        at.session_state['fixture_platform']='DraftKings'
        at.run(timeout=20).button(key='nba_build').click().run(timeout=20)
        self.assertFalse(at.exception)
        saved=at.session_state['nba_build_result']
        def export_disabled():
            return next(x for x in at.get('download_button') if x.proto.id.endswith('-nba_entries_download')).proto.disabled
        at.slider(key='nba_build_correlation').set_value(50).run(timeout=20)
        self.assertFalse(at.exception)
        self.assertFalse(export_disabled())
        self.assertEqual(at.session_state['test_build_calls'],1)
        at.number_input(key='nba_min_salary_DraftKings').set_value(48000).run(timeout=20)
        self.assertTrue(export_disabled())
        self.assertTrue(any('salary is outside limits' in x.value for x in at.error))
        at.number_input(key='nba_min_salary_DraftKings').set_value(0).run(timeout=20)
        self.assertFalse(export_disabled())
        player_id=str(saved['result']['portfolio'].iloc[0]['PG'])
        team=saved['pool'].set_index('Player ID').loc[player_id,'Team']
        at.multiselect(key='nba_excluded_teams_DraftKings').set_value([team]).run(timeout=20)
        self.assertTrue(export_disabled())
        self.assertTrue(any('excluded player' in x.value for x in at.error))
        at.multiselect(key='nba_excluded_teams_DraftKings').set_value([]).run(timeout=20)
        self.assertFalse(export_disabled())
        saved['contest_id']='not-the-selected-contest'
        at.session_state['nba_build_result']=saved
        at.run(timeout=20)
        self.assertTrue(export_disabled())
        self.assertTrue(any('contest used for this saved build' in x.value for x in at.error))
        saved['contest_id']='196711762'
        at.session_state['nba_build_result']=saved
        at.session_state['fixture_out_id']=str(saved['result']['portfolio'].iloc[0]['PG'])
        at.run(timeout=20)
        self.assertFalse(at.exception)
        self.assertTrue(export_disabled())
        self.assertTrue(any('OUT player' in x.value for x in at.error))
        self.assertEqual(at.session_state['test_build_calls'],1)

    def test_draftkings_uses_same_workspace_with_eight_slots(self):
        import sys
        from streamlit.testing.v1 import AppTest
        sys.path.insert(0,str(Path(__file__).parent))
        at=AppTest.from_file(str(Path(__file__).with_name('nba_ui_fixture.py')))
        at.session_state['fixture_platform']='DraftKings'
        at.run(timeout=20)
        self.assertFalse(at.exception)
        self.assertEqual(at.number_input(key='nba_min_salary_DraftKings').max,50000)
        self.assertEqual(at.slider(key='nba_build_correlation').value,0)
        at.button(key='nba_build').click().run(timeout=20)
        self.assertFalse(at.exception)
        built=at.session_state['nba_build_result']['result']
        self.assertEqual(built['candidates']['indices'].shape[1],8)
        self.assertEqual(len(built['portfolio']),3)
        at.slider(key='nba_exposure_diversity').set_value(100).run(timeout=20)
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['test_build_calls'],1)
        self.assertTrue(any('EXPORT TO DRAFTKINGS' in button.proto.label for button in at.get('download_button')))


