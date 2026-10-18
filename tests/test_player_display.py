import unittest
import pandas as pd
from simmah_player_display import complete_player_display

class DisplayTests(unittest.TestCase):
    def test_name_join_and_real_exposures(self):
        p=pd.DataFrame({'Name':['B','A','C']})
        outcomes=pd.DataFrame({'A':[10,20],'B':[2,4]})
        lineups=pd.DataFrame({'QB':['A','B'],'FLEX':['B','A']})
        r=complete_player_display(p,outcomes,lineups,lineups)
        self.assertEqual(r['Sim Pts'].tolist()[:2],[3,15])
        self.assertEqual(r['Mine Own %'].tolist(),[100,100,0])
        self.assertTrue(pd.isna(r['Sim Pts'].iloc[2]))
        self.assertTrue(r['Projected Own %'].isna().all())
    def test_pending_is_not_zero(self):
        r=complete_player_display(pd.DataFrame({'Name':['A']}))
        self.assertTrue(pd.isna(r['Mine Own %'].iloc[0]))
        self.assertTrue(pd.isna(r['Sim Pts'].iloc[0]))
    def test_special_slots_and_uploaded_zero(self):
        p=pd.DataFrame({'Name':['A','B'],'Projected Ownership':[0,40]})
        f=pd.DataFrame({'MVP':['A'],'FLEX1':['B']})
        r=complete_player_display(p,portfolio=f,field=f)
        self.assertEqual(r['Field MVP Own %'].tolist(),[100,0])
        self.assertEqual(r['Projected Own %'].tolist(),[0,40])

class ScoringInputReportTests(unittest.TestCase):
    def test_pending_placeholders_are_never_exported_as_completed_sims(self):
        from simmah_player_display import scoring_input_report
        players=pd.DataFrame({'Name':['A'],'Projection':[20.],'Sim Pts':[20.],'Sim P95':[36.],'Simulation Status':['Complete']})
        report=scoring_input_report(players)
        self.assertTrue(pd.isna(report['Sim Pts'].iloc[0]))
        self.assertTrue(pd.isna(report['Actual Simulation Mean'].iloc[0]))
        self.assertIn('Pending',report['Simulation Status'].iloc[0])

    def test_actual_latest_scores_replace_edited_placeholder_columns(self):
        from simmah_player_display import scoring_input_report
        players=pd.DataFrame({'Name':['B','A'],'Projection':[10.,20.],'Sim Pts':[10.,20.]})
        report=scoring_input_report(players,pd.DataFrame({'A':[12.,16.],'B':[1.,3.]}))
        self.assertEqual(report['Actual Simulation Mean'].tolist(),[2.,14.])
        self.assertEqual(report['Simulation Minus Projection'].tolist(),[-8.,-6.])
        self.assertEqual(report['Sim Pts'].tolist(),[2.,14.])
