"""Exercise the actual injury functions and fragment in a real Streamlit runtime."""
import ast
from pathlib import Path
import unittest

class InjuryStreamlitTests(unittest.TestCase):
    def test_out_player_stays_excluded_through_failed_feed_and_clears_on_recovery(self):
        from streamlit.testing.v1 import AppTest
        tree=ast.parse(Path('dfs_app.py').read_text());names={'normalize_injury_player_name','normalize_injury_team','apply_injury_statuses','lineup_export_download'}
        source='\n\n'.join(ast.unparse(n) for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names)
        harness='''
import pandas as pd
import streamlit as st
from zoneinfo import ZoneInfo
from simmah_nfl_injuries import InjuryStatuses
from simmah_session_state import safe_state_items
st.set_page_config(page_title='NFL injury test')
selected_format='DraftKings Classic'
_loaded_slate_tabs=None
_pinned_slates=None
workspace_stop=lambda *a:st.stop()
load_latest_automatic_pregame_snapshot=lambda *a:(pd.DataFrame(),{})
save_export_checkpoint=lambda *a:None
def workspace_download_button(st,*args,**kwargs):
    kwargs.pop('export_checkpoint',None)
    return st.download_button(*args,**kwargs)
'''+source+'''
def fail():st.session_state['feed_mode']='failure'
def recover():st.session_state['feed_mode']='healthy'
st.button('Simulate outage',on_click=fail)
st.button('Verified recovery',on_click=recover)
mode=st.session_state.get('feed_mode','out')
recovery_status=st.session_state.get('recovery_status','Active')
if mode=='failure':fetch_nfl_injury_statuses=lambda:({},'ESPN injury feed unavailable: timeout')
elif mode=='healthy':fetch_nfl_injury_statuses=lambda:(InjuryStatuses({('outplayer','DAL'):'Questionable'} if recovery_status=='Questionable' else {},covered_teams={'DAL'}),'ESPN NFL injury feed')
else:fetch_nfl_injury_statuses=lambda:(InjuryStatuses({('outplayer','DAL'):'Out'},covered_teams={'DAL'}),'ESPN NFL injury feed')
pool=pd.DataFrame({'Name':['Out Player','Healthy Player'],'Team':['DAL','DAL']})
current=apply_injury_statuses(pool,'test')
st.dataframe(current)
assigned=pd.DataFrame({'QB':['Out Player'],'Entry ID':['123']})
lineup_export_download('Export entries',b'Entry ID,QB\n123,99','entries.csv',portfolio=assigned,slots=['QB'])
'''
        # Keep the fixture's embedded CSV newline escaped in the app source.
        harness=harness.replace("b'Entry ID,QB\n123,99'","b'Entry ID,QB\\n123,99'")
        for recovery_status in ['Active','Questionable']:
            with self.subTest(recovery_status=recovery_status):
                app=AppTest.from_string(harness)
                app.session_state['recovery_status']=recovery_status
                app.run(timeout=15)
                self.assertFalse(app.exception)
                self.assertEqual(app.dataframe[0].value.Name.tolist(),['Healthy Player'])
                self.assertTrue(any(x.value == 'Export blocked — these assigned lineups contain OUT players: Out Player. Refresh injury news and rebuild the portfolio. Saved entries were not changed.' for x in app.error))
                app.button[0].click().run(timeout=15)
                self.assertFalse(app.exception)
                self.assertEqual(app.dataframe[0].value.Name.tolist(),['Healthy Player'])
                self.assertTrue(any('Last known' in x.value for x in app.warning))
                self.assertTrue(any(x.value == 'Export blocked — these assigned lineups contain OUT players: Out Player. Refresh injury news and rebuild the portfolio. Saved entries were not changed.' for x in app.error))
                app.button[1].click().run(timeout=15)
                self.assertFalse(app.exception)
                self.assertEqual(app.dataframe[0].value.Name.tolist(),['Out Player','Healthy Player'])
                self.assertFalse(app.error)
                self.assertEqual(len(app.get('download_button')),1)
                self.assertEqual(app.session_state['player_injury_statuses']['Out Player'],recovery_status)
                self.assertEqual(app.dataframe[0].value.set_index('Name').loc['Out Player','Injury Status'],recovery_status)


if __name__=='__main__':unittest.main()
