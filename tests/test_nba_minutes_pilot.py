import importlib.util
from pathlib import Path
import sys
import unittest
import json
import pandas as pd
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from nba_minutes_pilot import evaluate

class HistoricalMinutesPilotTests(unittest.TestCase):
    def records(self):
        rows=[]
        for day in range(1,9):
            for i in range(8):
                rows.append({'Game Date':f'2025-01-{day:02d}','ESPN Game ID':str(day),'ESPN Team ID':'1',
                    'ESPN Player ID':str(i),'Name':str(i),'Regulation Minutes':30.,'Actual Status':'played'})
        return pd.DataFrame(rows)
    def test_holdout_result_cannot_change_its_own_forecast(self):
        actual=self.records();_,baseline,_=evaluate(actual)
        actual.loc[(actual['Game Date']=='2025-01-08') & (actual['ESPN Player ID']=='0'),'Regulation Minutes']=40
        actual.loc[(actual['Game Date']=='2025-01-08') & (actual['ESPN Player ID']=='1'),'Regulation Minutes']=20
        summary,changed,_=evaluate(actual)
        self.assertEqual(baseline['Mean Minutes'].tolist(),changed['Mean Minutes'].tolist())
        self.assertEqual(summary['matched_player_games'],8)
        self.assertGreater(summary['mae'],0)
        self.assertEqual(changed['Prior Team Games'].unique().tolist(),[5])
        json.dumps(summary,allow_nan=False)
    def test_incomplete_actual_ledger_rejected(self):
        actual=self.records();actual.loc[0,'Regulation Minutes']=0
        with self.assertRaises(ValueError):evaluate(actual)
