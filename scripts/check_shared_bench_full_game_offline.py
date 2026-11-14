"""Single-slate distribution diagnostic, never a winner-driven tuning loop."""
import argparse,hashlib,io,json,sys,time,zipfile
from pathlib import Path
from unittest.mock import patch
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from simmah_nba_pregame import PregameEngine
from simmah_nba_engine import EventRates
from simmah_nba_shared_bench_offline import draw_bench_minutes


def run(archive,lineup_file,output):
    with zipfile.ZipFile(archive) as z:
        # The saved production draws are a valid control only for identical
        # physical source code. Never silently compare a different engine.
        checked=[]
        for name in ['simmah_nba_engine.py','simmah_nba_pregame.py','simmah_nba_markets.py',
            'simmah_nba_projection_anchor.py','simmah_nba_rotation_schedule.py','simmah_nba_scoring.py',
            'simmah_nba_minutes.py','simmah_nba_overtime_rotations.py']:
            if z.read('implementation/'+name)!=(ROOT/name).read_bytes():raise ValueError('Frozen engine differs: '+name)
            checked.append(name)
        meta=json.loads(z.read('inputs/player_pool.json'));pool=pd.DataFrame(meta['rows']);pool.attrs=meta['attrs']
        if not pool.attrs.get('nba_variable_minutes') or not pool.attrs.get('nba_wider_minutes'):raise ValueError('Requires saved wider+variable control')
        settings=json.loads(z.read('inputs/settings.json'));markets=json.loads(z.read('inputs/markets.json'));rates=EventRates(**json.loads(z.read('inputs/engine.json'))['rates'])
        with np.load(io.BytesIO(z.read('solver/arrays.npz'))) as arrays:baseline=arrays['outcomes_seed_2100'].copy()
        baseline_reports=json.loads(z.read('solver/diagnostics.json'))['engine_reports']['2100']
    names=json.loads(Path(lineup_file).read_text())['pool_best_players'];indices=[]
    for name in names:
        matched=np.flatnonzero(pool.Name==name)
        if len(matched)!=1:raise ValueError('Ambiguous diagnostic lineup')
        indices.append(int(matched[0]))
    started=time.perf_counter();engine=PregameEngine(pool,markets,rates,platform='DraftKings',parallel=False)
    with patch('simmah_nba_pregame.draw_wider_minutes',draw_bench_minutes):
        # Match production's construction-first calibration basis, then draw
        # an independent evaluation set. No cached draws cross research arms.
        engine(settings['simulations'],settings['seed'])
        changed=engine(settings['simulations'],settings['seed']+2017)
    active=np.unique(np.concatenate([g[0] for _,groups in engine.games for g in groups]));active=active[pool.iloc[active].Projection.to_numpy(float)>0]
    targets=pool.iloc[active].Projection.to_numpy(float)
    def metrics(x,reports):
        total=x[:,indices].sum(1);means=x[:,active].mean(0,dtype=np.float64);errors=abs(means-targets)
        return {'lineup_mean':float(total.mean()),'lineup_p99':float(np.quantile(total,.99)),
            'trials_at_least_340':int((total>=340).sum()),'trials':len(total),
            'player_mean_mae':float(errors.mean()),'player_max_mean_error':float(errors.max()),
            'player_mean_errors_over_max05_or5pct':int((errors>np.maximum(.5,.05*targets)).sum()),
            'max_team_total_residual':float(max(abs(v) for r in reports for v in (r['calibration']['residual'] or [0]))),
            'Jackson_Hendricks_FP_correlation':float(np.corrcoef(x[:,indices[names.index('Gregory Jackson')]],x[:,indices[names.index('Taylor Hendricks')]])[0,1])}
    result={'live_enabled':False,'scope':'Known November 13 development lineup; mechanics diagnostic only, no candidate regeneration, contest-field rebuild or portfolio promotion',
        'source_code_parity_checked':checked,'source_archive_sha256':hashlib.sha256(Path(archive).read_bytes()).hexdigest(),
        'construction_seed':settings['seed'],'evaluation_seed':settings['seed']+2017,
        'baseline':metrics(baseline,baseline_reports),'shared':metrics(changed,engine.last_report),'seconds_shared_replay':time.perf_counter()-started}
    Path(output).write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('archive');p.add_argument('lineup_file');p.add_argument('output');a=p.parse_args();run(a.archive,a.lineup_file,a.output)
