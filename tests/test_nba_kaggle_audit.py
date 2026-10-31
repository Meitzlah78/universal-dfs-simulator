import importlib.util
from pathlib import Path
import tempfile
import unittest
import pandas as pd

spec=importlib.util.spec_from_file_location('kaggle_audit',Path(__file__).parents[1]/'scripts/nba_kaggle_audit.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class KaggleAuditTests(unittest.TestCase):
    def test_complete_ledgers_and_explicit_dnp(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            pd.DataFrame([{'gameId':'123','gameDateTimeEst':'2025-01-01 19:00:00','gameType':'Regular Season'}]).to_csv(folder/'Games.csv',index=False)
            players=[];teams=[]
            for team in ['1','2']:
                teams.append({'gameId':'123','teamId':team,'numMinutes':240,'teamScore':50})
                for i in range(6):
                    players.append({'gameId':'123','personId':team+str(i),'playerteamId':team,
                        'gameDateTimeEst':'2025-01-01 19:00:00','numMinutes':48 if i<5 else None,
                        'comment':None if i<5 else "DNP - Coach's Decision",'points':10 if i<5 else 0,
                        **{k:0 for k in ['assists','blocks','steals','reboundsTotal','turnovers','fieldGoalsMade','threePointersMade','freeThrowsMade']}})
            pd.DataFrame(players).to_csv(folder/'PlayerStatistics.csv',index=False)
            pd.DataFrame(teams).to_csv(folder/'TeamStatistics.csv',index=False)
            result=module.audit(folder)
            self.assertEqual(result['minutes_ledgers_reconciled'],2)
            self.assertEqual(result['points_ledgers_reconciled'],2)
            self.assertEqual(result['explicit_nonparticipation_rows'],2)
            self.assertEqual(result['unresolved_minutes_rows'],0)
