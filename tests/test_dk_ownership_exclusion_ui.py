import ast
from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest


class DKOwnershipExclusionUITest(unittest.TestCase):
    def test_missing_role_players_can_be_explicitly_removed_before_preflight(self):
        tree=ast.parse(Path('dfs_app.py').read_text())
        blocks=[n for n in ast.walk(tree) if isinstance(n,ast.If)
                and ast.unparse(n.test)=="lineup_mode == 'Showdown'"
                and any(isinstance(c,ast.Call) and isinstance(c.func,ast.Name)
                        and c.func.id=='render_role_exclusions' for c in ast.walk(n))]
        self.assertEqual(len(blocks),1)
        app='''import streamlit as st
import pandas as pd
from simmah_fantasylabs_ownership import role_preferences
lineup_mode='Showdown'
players_df=pd.DataFrame({'Name':['Covered','Lew Nichols','Brandon Smith','Riley Nowakowski'],
 'Team':['PIT','PIT','CIN','PIT'],'Projected CPT Own %':[10.,None,None,None],
 'Projected Flex Ownership':[50.,None,None,None]})
players_df.attrs['fantasylabs_ownership']={'site':'DraftKings','format':'single_game','slate_date':'2026-11-15','sha256':'fixture'}
_tab_roster=st.container()
'''+ast.unparse(blocks[0])+'''
st.session_state['surviving_names']=players_df.Name.tolist()
try:
 role_preferences(players_df)
 st.success('Ownership preflight passed')
except ValueError as exc:st.error(str(exc))
'''
        at=AppTest.from_string(app).run()
        self.assertFalse(at.exception)
        self.assertEqual(at.multiselect[0].label,'Exclude from BOTH my lineups and simulated opponents')
        self.assertEqual(len(at.error),1)
        at.multiselect[0].set_value(['Lew Nichols','Brandon Smith','Riley Nowakowski']).run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['surviving_names'],['Covered'])
        self.assertEqual(len(at.error),0)
        self.assertEqual(at.success[0].value,'Ownership preflight passed')


if __name__=='__main__':unittest.main()
