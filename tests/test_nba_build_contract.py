"""Offline build-to-export contract. Fixtures never substitute for live feeds."""
import csv
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd

from simmah_nba_import import read_template,SLOTS
from simmah_nba_pregame import PregameEngine,ROLE_COLUMNS,validate_game_reports
from simmah_nba_projections import apply_rotowire_projections,parse_rotowire
from simmah_nba_role_priors import apply_position_priors
from simmah_nba_pool_overrides import requested_pool_exclusions
from simmah_nba_engine import EventRates
from simmah_nba_pipeline import run_pipeline,export_portfolio
from simmah_nba_rosters import validate_lineup


def fixture():
    """Complete four-team FanDuel entry/salary upload and provider responses."""
    rows=[['entry_id','contest_id','contest_name','entry_fee',*SLOTS,'keep']]
    rows += [[str(900+i),'42-99','Offline regression','.10',*(['']*9),'original'] for i in range(20)]
    rows += [['999','42-100','Other contest','.10',*(['']*9),'untouched']]
    rows.append(['Id','Nickname','Salary','Position','Team','Opponent','Game','Injury Indicator','Injury Details','FPPG'])
    players=[];points=[];ownership=[]
    for i in range(40):
        team=['DAL','IND','NY','PHI'][i//10];opp={'DAL':'IND','IND':'DAL','NY':'PHI','PHI':'NY'}[team]
        name='Sergio De Larrea' if i==0 else 'Fixture '+str(i)
        pos=['PG','SG','SF','PF','C'][i%5]
        rows.append(['42-'+str(i),name,'6500',pos,team,opp,team+'@'+opp,'','','0'])
        first,last=name.split(' ',1)
        players.append({'slateID':str(i),'firstName':first,'lastName':last,
            'team':{'abbr':team},'opponent':{'team':opp},
            'game':{'dateTime':'2026-10-23 19:00:00'},
            'minutes':[7,27,27,27,27,25,25,25,25,25][i%10],
            'stats':{'season':dict(minutes=10,**dict.fromkeys(['fga','ast','reb','stl','blk'],0 if i==6 else 1))}})
        points.append({'slateID':str(i),'pts':5 if i%10==0 else 30})
        ownership.append({'slateID':str(i),'rst':0 if i%10==0 else 900/36})
    f=io.StringIO();csv.writer(f).writerows(rows);raw=f.getvalue().encode()
    pool=read_template(raw)['players'];pool.attrs['slate_date']='2026-10-23'
    values,details=parse_rotowire(players,{'access':True,'source':'RotoWire','projections':points},
        '2026-10-23',pool,{'access':True,'source':'RotoWire','rostership':ownership})
    pool=apply_rotowire_projections(pool,values,details)
    pool,_=requested_pool_exclusions(pool,'2026-10-23','FanDuel')
    model=json.loads((Path(__file__).parents[1]/'data/nba_models/position-roles-before-2026-04-09.json').read_text())
    pool=apply_position_priors(pool,model,'2026-10-23')
    rates=EventRates(.12,.1,.4,.53,.36,.78,.6,.25,.6,.1,13)
    return raw,pool,rates


class BuildContractTests(unittest.TestCase):
    # Use a complete 20-entry fixture with ten players per team so ownership
    # and low-minute hard caps admit a legal portfolio without relaxing them.

    def run_build(self,simulations,candidates,support,entries=200):
        raw,pool,rates=fixture()
        from simmah_nba_simulation_cache import CachedNBAOutcomes,clear_simulation_cache
        from simmah_nba_ownership import field_ownership_inputs
        clear_simulation_cache()
        self.addCleanup(clear_simulation_cache)
        self.assertFalse(pool.loc[0,'Eligible'])
        self.assertEqual(pool.loc[0,'Projected Minutes'],7)
        self.assertIn('Position prior',pool.loc[6,'Role Rate Source'])
        self.assertTrue(pool.groupby('Team')['Projected Minutes'].sum().eq(240).all())
        engine=CachedNBAOutcomes(PregameEngine(pool,[],rates,parallel=False))
        own=field_ownership_inputs(pool);self.assertEqual(own['mode'],'projected')
        result=run_pipeline(pool,engine,own['weights'],own['source'],[10]+[0]*entries,.10,20,
            simulations=simulations,candidate_target=candidates,field_support_target=support,salary_min=58000)
        self.assertEqual(result['simulations_per_set'],simulations)
        self.assertEqual(result['candidates']['unique'],candidates)
        self.assertEqual(result['field']['copies'].sum(),entries)
        self.assertEqual(result['report'].attrs['simulations'],simulations)
        self.assertEqual(len(result['portfolio']),20)
        self.assertEqual(len(set(result['simulation_seeds'].values())),3)
        for ids in [result['candidates']['indices'],result['field']['indices']]:
            self.assertFalse((ids==0).any())
        output=export_portfolio(raw,'42-99',pool,result)
        before=list(csv.reader(io.StringIO(raw.decode())));after=list(csv.reader(io.StringIO(output.decode())))
        self.assertEqual(before[21:],after[21:])
        for a,b in zip(before[1:21],after[1:21]):
            self.assertEqual(a[:4],b[:4]);self.assertEqual(a[13:],b[13:])
            validate_lineup(pool,b[4:13],salary_cap=60000,max_from_team=4,salary_min=58000)
        return result

    def test_import_simulation_field_portfolio_and_export(self):
        self.run_build(64,500,500)

    @unittest.skipUnless(os.environ.get('SIMMAH_NBA_FULL_SCALE')=='1','full-scale replay runs in its dedicated CI step')
    def test_full_scale_build_to_export(self):
        result=self.run_build(10000,5000,10000,entries=20000)
        print('FULL_SCALE_NBA',json.dumps(result['timings_seconds'],sort_keys=True),flush=True)

    def test_preflight_lists_problems_for_multiple_teams(self):
        _,pool,rates=fixture()
        pool.loc[1,'Projected Minutes']=np.nan
        pool.loc[11,'Projected Minutes']=49
        pool.loc[22,ROLE_COLUMNS]=0
        with self.assertRaises(ValueError) as caught:PregameEngine(pool,[],rates,parallel=False)
        message=str(caught.exception)
        for label in ['DAL','Fixture 1','IND','Fixture 11','NY','Fixture 22']:
            self.assertIn(label,message)

    def test_bad_simulations_fail_before_candidate_search(self):
        _,pool,_=fixture()
        class Factory:
            last_report=[{'teams':('DAL','IND'),'calibration':{'applied':True,'within_four_points':False},'unresolved_tie_fraction':0}]
            def __call__(self,n,seed):return np.ones((n,len(pool)))
        with patch('simmah_nba_pipeline.build_candidates') as build:
            with self.assertRaisesRegex(ValueError,'DAL vs IND'):
                run_pipeline(pool,Factory(),np.ones(len(pool)),'fixture',[1,0],.1,1,simulations=2)
            build.assert_not_called()

    def test_unpriced_games_are_valid_and_unresolved_overtime_is_not(self):
        report={'teams':('DAL','IND'),'calibration':{'applied':False,'within_four_points':None},'unresolved_tie_fraction':0}
        validate_game_reports([report])
        report['unresolved_tie_fraction']=.01
        with self.assertRaisesRegex(ValueError,'unresolved overtime'):validate_game_reports([report])


if __name__=='__main__':unittest.main()
