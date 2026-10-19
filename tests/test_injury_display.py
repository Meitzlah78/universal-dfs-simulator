import unittest
from types import SimpleNamespace
import pandas as pd
from simmah_injury_display import injury_frame, injury_label, injury_player_pool
class InjuryDisplayTests(unittest.TestCase):
    def test_markers_are_display_only(self):
        original=pd.DataFrame({'Captain':['A'],'Flex1':['B'],'Salary':[49000]})
        st=SimpleNamespace(session_state={'display_injury_statuses':{'A':'Questionable','B':'Doubtful'}})
        shown=injury_frame(st,original)
        self.assertEqual(shown.Captain.iloc[0],'A [Q]');self.assertEqual(shown.Flex1.iloc[0],'B [D]')
        self.assertEqual(original.Captain.iloc[0],'A');self.assertEqual(shown.Salary.iloc[0],49000)
    def test_pool_status_overrides_feed(self):
        st=SimpleNamespace(session_state={'display_injury_statuses':{'A':'Questionable'}})
        frame=pd.DataFrame({'Name':['A'],'Injury Status':['Doubtful']})
        self.assertEqual(injury_frame(st,frame).Name.iloc[0],'A [D]')
        self.assertEqual(injury_label('Healthy',{}),'Healthy')

    def test_roster_badges_preserve_canonical_names(self):
        pool=pd.DataFrame({'Name':['A','B'],'Injury Status':['Questionable','Doubtful']})
        shown=injury_player_pool(pool)
        self.assertEqual(shown.Player.tolist(),['A [Q]','B [D]'])
        self.assertEqual(shown.Name.tolist(),['A','B'])
        from simmah_ui import player_columns
        self.assertEqual(player_columns(shown)[0],'Player')
