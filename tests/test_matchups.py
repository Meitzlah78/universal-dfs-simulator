import unittest
import pandas as pd
from simmah_matchups import matchup_inputs, dated_history

class MatchupTests(unittest.TestCase):
    def fixture(self):
        games=[]; rows=[]
        for i in range(1,7):
            games.append(dict(game_id=str(i),gameday=f'2026-09-{i:02}'))
            for opponent,yards in [('DAL',200),('GB',100)]:
                rows.append(dict(game_id=str(i),position='WR',opponent_team=opponent,
                    receptions=10,receiving_yards=yards,carries=0,rushing_yards=0))
        pool=pd.DataFrame([dict(Name='Receiver',Position='WR',Opponent='DAL', **{'Weather Kickoff':'2026-09-07T20:00:00Z'})])
        return pool,pd.DataFrame(rows),pd.DataFrame(games)

    def test_pregame_only(self):
        p,h,s=self.fixture()
        data=dated_history(h,s,'2026-09-04T20:00:00Z')
        self.assertEqual(set(data.game_id),{'1','2','3'})

    def test_shrink_cap_and_source_date(self):
        p,h,s=self.fixture(); values,report=matchup_inputs(p,h,s)
        self.assertEqual(values['Receiver']['matchup_receiving'],1.1)
        self.assertEqual(report.iloc[0]['Through'],'2026-09-06')
        self.assertEqual(report.iloc[0]['Games'],6)

    def test_neutral_missing_kickoff_and_short_sample(self):
        p,h,s=self.fixture();p['Weather Kickoff']=''
        self.assertEqual(matchup_inputs(p,h,s)[0]['Receiver'],{})
        p['Weather Kickoff']='2026-09-03T20:00:00Z'
        self.assertEqual(matchup_inputs(p,h,s)[0]['Receiver'],{})

    def test_sack_rate_is_shrunk_and_bounded(self):
        p,h,s=self.fixture()
        p['Position']='QB';h['position']='QB'
        h['attempts']=30;h['sacks_suffered']=9
        values,report=matchup_inputs(p,h,s)
        self.assertEqual(values['Receiver']['matchup_sack_rate'],.09)

    def test_future_changes_cannot_change_matchup(self):
        p,h,s=self.fixture();p['Weather Kickoff']='2026-09-05T20:00:00Z'
        original=matchup_inputs(p,h,s)[0]
        h.loc[h.game_id.eq('6'),'receiving_yards']=999999
        self.assertEqual(original,matchup_inputs(p,h,s)[0])

if __name__=='__main__': unittest.main()
