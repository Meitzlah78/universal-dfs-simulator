"""Seeded full-stat parity against the engine before the pipeline speed changes."""
import hashlib
import json
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
from simmah_nfl_engine import simulate_stat_lines
from test_nfl_engine import fixture


def cases():
    pool,roles=fixture()
    for site in ('FanDuel','DraftKings'):
        for mode in ('baseline','learned','thin','concentrated','rb-only'):
            players=pool if mode!='thin' else pool[pool.Position.isin(['RB','K','DST'])]
            case_roles=roles
            if mode=='rb-only':
                players=pool[pool.Position.isin(['RB','K','DST'])].copy()
                extra=pool[pool.Position.eq('RB')].copy();extra['Name']+='-backup';extra['Projection']*=.4
                players=pd.concat([players,extra],ignore_index=True)
                case_roles=dict(roles,**{name:dict(carries=3,targets=8,receptions=5,rush_yards=14,rec_yards=45) for name in extra.Name})
            learned={} if mode in ('baseline','thin') else {'rushing_df':3.,'rushing_sd':6.}
            if mode=='concentrated':learned['opportunity_concentration']=30.
            yield f'{site}-{mode}',players,case_roles,site,learned,1 if mode=='thin' else 257


def outcome_digest(fn,pool,roles,site,learned,count):
    rng=np.random.default_rng(91037)
    stats,diagnostics=fn(pool,roles,rng,count,scoring_platform=site,
        learned_parameters=learned,return_diagnostics=True,
        weather_by_team={'A':{'status':'Available','wind_mph':15,'precip_pct':30}},
        market_gain={'A':1.1,'B':.9})
    h=hashlib.sha256()
    for tables in (stats,diagnostics):
        for name,table in tables.items():
            for key,values in table.items():
                a=np.asarray(values)
                h.update(json.dumps([name,key,str(a.dtype),a.shape]).encode());h.update(a.tobytes())
    h.update(json.dumps(rng.bit_generator.state,sort_keys=True).encode())
    return h.hexdigest()


class PipelineParityTests(unittest.TestCase):
    def test_all_stats_diagnostics_and_rng_state_match_original(self):
        expected=json.loads(Path('tests/fixtures/nfl-pipeline-original-hashes.json').read_text())
        for name,pool,roles,site,learned,count in cases():
            with self.subTest(name=name):
                self.assertEqual(outcome_digest(simulate_stat_lines,pool,roles,site,learned,count),expected['cases'][name])

if __name__=='__main__':unittest.main()
