"""Bounded process-local cache of deterministic NBA game outcomes, no UI IO.

Keys include every physical simulation input. Salaries, ownership and user
exclusions do not change basketball outcomes and are deliberately excluded.
Cached draws retain distinct construction, field and evaluation seeds.
"""
from collections import OrderedDict
from copy import deepcopy
from hashlib import sha256
from threading import Lock
import json
import pandas as pd
from pathlib import Path

_records=OrderedDict()
_lock=Lock()
_MAX_SLATES=2


def simulation_identity(engine):
    from simmah_nba_pregame import ROLE_COLUMNS
    columns=['Player ID','Team','Opponent','Projection','Injury Status','Projected Minutes',*ROLE_COLUMNS]
    inputs=engine.pool[columns]
    implementation=sha256()
    for name in ('simmah_nba_engine.py','simmah_nba_pregame.py','simmah_nba_markets.py',
                 'simmah_nba_projection_anchor.py','simmah_nba_rotation_schedule.py','simmah_nba_scoring.py'):
        implementation.update(Path(__file__).with_name(name).read_bytes())
    payload={'version':1,'platform':engine.platform,'max_overtimes':engine.max_overtimes,
        'implementation':implementation.hexdigest(),
        'pool':sha256(pd.util.hash_pandas_object(inputs,index=False).to_numpy().tobytes()).hexdigest(),
        'dtypes':list(map(str,inputs.dtypes)),
        'games':[market for market,_ in engine.games],'rates':vars(engine.rates)}
    return sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()


class CachedNBAOutcomes:
    def __init__(self,engine,construction_seed=83):
        self.engine=engine;self.identity=simulation_identity(engine)
        self.construction_seed=construction_seed;self.last_report=[];self.last_cache_hit=False

    def __getattr__(self,name):return getattr(self.engine,name)

    def __call__(self,n,seed):
        if seed not in {self.construction_seed,self.construction_seed+1009,self.construction_seed+2017}:
            values=self.engine(n,seed);self.last_report=deepcopy(self.engine.last_report)
            self.last_cache_hit=False;return values
        key=(self.identity,n,self.construction_seed)
        with _lock:
            record=_records.get(key)
            if record is None:
                record={'engine':self.engine,'draws':{},'lock':Lock()};_records[key]=record
                while len(_records)>_MAX_SLATES:_records.popitem(last=False)
            else:_records.move_to_end(key)
        with record['lock']:
            self.last_cache_hit=seed in record['draws']
            if not self.last_cache_hit:
                # Pipeline calls construction first; preserve that calibration
                # basis when restoring another engine wrapper on a later rerun.
                if not record['draws'] and seed!=self.construction_seed:
                    raise ValueError('Cached NBA draws must start with the construction seed')
                values=record['engine'](n,seed)
                values.setflags(write=False)
                record['draws'][seed]=(values,deepcopy(record['engine'].last_report))
            values,report=record['draws'][seed]
            self.last_report=deepcopy(report)
            return values.view()


def clear_simulation_cache():
    with _lock:_records.clear()
