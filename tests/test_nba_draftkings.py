import csv,io,unittest
import numpy as np
import pandas as pd
from simmah_nba_import import read_template
from simmah_nba_rules import DK_SLOTS,rules_for
from simmah_nba_scoring import score_draftkings,score_fanduel
from simmah_nba_candidates import build_candidates
from simmah_nba_rosters import export_entries,validate_lineup
from simmah_nba_pipeline import run_pipeline,export_portfolio
from simmah_nba_late_swap import swap_entries,export_swaps
from simmah_nba_contest import evaluate_candidates
from simmah_nba_projections import player_key


def template():
    rows=[['Entry ID','Contest Name','Contest ID','Entry Fee',*DK_SLOTS,'','Instructions']]
    for i in range(3):rows.append([str(100+i),'NBA fixture','196711762','$0.25',*['']*8,'','keep'])
    rows.append(['']*13+['Position','Name + ID','Name','ID','Roster Position','Salary','Game Info','TeamAbbrev','AvgPointsPerGame'])
    for i in range(40):
        pos=['PG','SG','SF','PF','C'][i%5];team=['NYK','PHI','SAS','OKC'][i%4];game='PHI@NYK 10/20/2026 07:00PM ET' if team in {'NYK','PHI'} else 'OKC@SAS 10/20/2026 09:30PM ET'
        rows.append(['']*13+[pos,f'Player {i} ({1000+i})',f'Player {i}',str(1000+i),pos+'/UTIL','5000',game,team,'40'])
    f=io.StringIO();csv.writer(f).writerows(rows);return f.getvalue().encode()

class DraftKingsNBATests(unittest.TestCase):
    def test_persisted_contest_clock_recovery_without_session(self):
        from unittest.mock import patch
        from pathlib import Path
        import json
        data=template().replace(b'PHI@NYK 10/20/2026 07:00PM ET',b'In Progress')
        saved={'contest_id':'196711762','players':self.pool[['Player ID','Team','Opponent','Game Start','Salary']].to_dict('records')}
        with patch.object(Path,'exists',return_value=True),patch.object(Path,'read_text',return_value=json.dumps(saved)):
            parsed=read_template(data)
        self.assertEqual(len(parsed['entries']),3)
        self.assertEqual(parsed['players'].loc[0,'Game Start'],self.pool.loc[0,'Game Start'])
    def test_late_swap_recovers_missing_clocks_from_original_upload(self):
        from simmah_nba_late_swap import restore_late_swap_clocks,locked_players
        current=self.pool.copy();current['Game Start']=None
        restored=restore_late_swap_clocks(current,self.data)
        self.assertEqual(restored['Game Start'].tolist(),self.pool['Game Start'].tolist())
        self.assertTrue(current['Game Start'].isna().all())
        self.assertTrue(locked_players(restored,pd.Timestamp('2026-10-22T00:00:00Z')).all())
    def test_started_game_entries_use_existing_slate_context(self):
        from simmah_nba_late_swap import entry_rows
        data=template().replace(b'PHI@NYK 10/20/2026 07:00PM ET',b'In Progress')
        data=data.replace(b'$0.25,,,,,,,,,',b'$0.25,Player (1000) (LOCKED),1001,1002,1003,1004,1005,1006,1007,',1)
        slate=read_template(data,game_context_pool=self.pool)
        self.assertEqual(slate['entries'][0][4], '1000')
        self.assertEqual(slate['players'].loc[0,'Game Start'], self.pool.loc[0,'Game Start'])
        legacy=self.pool.copy()
        legacy['Game Start']=legacy['Game Start'].map(lambda x:pd.Timestamp(x).tz_localize(None).isoformat())
        self.assertEqual(read_template(data,game_context_pool=legacy)['entries'][0][4], '1000')
        with self.assertRaises(ValueError):read_template(data)
        wrong=self.pool.copy();wrong.loc[0,'Salary']=6000
        with self.assertRaises(ValueError):read_template(data,game_context_pool=wrong)
    def test_locked_entry_player_ids(self):
        from simmah_nba_dk_import import player_id
        self.assertEqual(player_id('Neemias Queta (44670178) (LOCKED)'), '44670178')
        self.assertEqual(player_id('44670178 (LOCKED)'), '44670178')
        self.assertEqual(player_id('Player (123) (locked)  '), '123')
        for invalid in ['Player (LOCKED)', 'Player (123) garbage', '(LOCKED)']:
            with self.assertRaises(ValueError):player_id(invalid)
        data=template().replace(b'$0.25,,,,,,,,,', b'$0.25,Player 0 (1000) (LOCKED),,,,,,,,', 1)
        self.assertEqual(read_template(data)['entries'][0][4], '1000')
    def setUp(self):
        self.data=template();self.slate=read_template(self.data);self.pool=self.slate['players'];self.pool['Projection']=30.;self.pool['Eligible']=True
    def test_site_date_ids_and_bonus_scoring(self):
        self.assertEqual(self.slate['date'],'2026-10-20');self.assertEqual(self.slate['slots'],DK_SLOTS)
        self.assertEqual(rules_for(self.pool)['salary_cap'],50000)
        self.assertEqual(score_draftkings(points=20,threes=3,rebounds=10,assists=10,steals=2,blocks=1,turnovers=4),57.5)
        self.assertEqual(score_fanduel(points=20,rebounds=10,assists=10,steals=2,blocks=1,turnovers=4),52)
        self.assertEqual(player_key('Labaron Philon Jr.','NYK'),player_key('Labaron Philon','NY'))
    def test_pipeline_export_and_late_swap_preserve_original_cells(self):
        calls=[]
        def draw(n,seed):calls.append(seed);return np.random.default_rng(seed).gamma(5,6,(n,len(self.pool)))
        r=run_pipeline(self.pool,draw,np.ones(40)*20,'synthetic estimated popularity',np.r_[10,5,np.zeros(18)],.25,3,
            simulations=30,candidate_target=50,field_support_target=60,ownership_mode='relative popularity')
        self.assertEqual(len(set(calls)),3);self.assertEqual(r['candidates']['indices'].shape,(50,8))
        self.assertAlmostEqual(r['field']['ownership_sampled'].sum(),800)
        export=export_portfolio(self.data,'196711762',self.pool,r)
        source=list(csv.reader(io.StringIO(self.data.decode())));output=list(csv.reader(io.StringIO(export.decode())))
        self.assertEqual(output[4:],source[4:])
        for before,after in zip(source[1:4],output[1:4]):
            self.assertEqual(before[:4],after[:4]);self.assertEqual(before[12:],after[12:])
            validate_lineup(self.pool,after[4:12],salary_cap=50000,max_from_team=8)
        now=pd.Timestamp('2026-10-21T00:00:00Z');sw=swap_entries(export,'196711762',self.pool,now=now)
        swapped=read_template(export_swaps(export,'196711762',self.pool,sw,now=now))
        lookup=self.pool.set_index('Player ID')
        for before,after in zip(read_template(export)['entries'],swapped['entries']):
            for j,pid in enumerate(before[4:12]):
                if lookup.loc[pid,'Team'] in {'NY','PHI'}:self.assertEqual(pid,after[4+j])
    def test_dk_quarter_point_ties_not_rounded_to_tenths(self):
        outcomes=np.zeros((1,16));outcomes[0,0]=.25;outcomes[0,8]=.5
        result=evaluate_candidates(outcomes,np.arange(8)[None,:],np.arange(8,16)[None,:],np.array([10,0]),1,construction_seed=1,evaluation_seed=2,score_ticks=4)
        self.assertEqual(result['Expected Prize ($)'].iloc[0],0)
        self.assertEqual(result['Evaluation Mean Points'].iloc[0],.25)
    def test_single_game_rejected_and_wrong_slots(self):
        pool=self.pool.copy();pool['Team']=np.where(np.arange(40)%2,'NY','PHI');pool['Opponent']=np.where(pool.Team.eq('NY'),'PHI','NY')
        c=build_candidates(pool,np.ones((3,40)),target=5,max_attempts=1024)
        self.assertEqual(c['unique'],0)
        with self.assertRaises(ValueError):read_template(self.data.replace(b'PG,SG,SF,PF,C,G,F,UTIL',b'PG,SG,SF,PF,C,G,F,CPT'))
