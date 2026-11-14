"""Summarize matched paired replays; physical-game bootstrap, no row independence."""
import json,sys
from pathlib import Path
import numpy as np,pandas as pd

def ci(g):
    if not len(g):return None
    x=g.to_numpy(float);rng=np.random.default_rng(210019)
    return {'game_weighted_delta':float(x.mean()),'bootstrap95':np.quantile(x[rng.integers(len(x),size=(2000,len(x)))].mean(1),[.025,.975]).tolist(),'games':len(x)}
def run(root):
    root=Path(root);out=root/'minutes-coupled-cv'
    arms={arm:pd.concat([pd.read_csv(p,dtype={'package':str,'game_id':str}) for p in out.glob('*_'+arm+'_fp.csv')],ignore_index=True) for arm in ['independent','coupled']}
    keys=['package','game_id','team','name'];a=arms['independent'];b=arms['coupled'];f=a.merge(b,on=keys,suffixes=('_independent','_coupled'),validate='one_to_one')
    if len(f)!=len(a) or len(f)!=len(b):raise ValueError('Incomplete paired replay')
    f['delta']=f.covered_coupled.astype(float)-f.covered_independent.astype(float)
    result={'scope':'Fresh current-engine controls; variable+wider minutes enabled in both arms; each arm independently runs pregame calibration with seed83, then2000 evaluation trials seed2100','rows':len(f),'builds':f.package.nunique(),'games':f.game_id.nunique(),'platforms':{}}
    for site,g in f.groupby('platform_independent'):
        def metrics(x):
            return {'n':len(x),'independent':float(x.covered_independent.mean()),'coupled':float(x.covered_coupled.mean()),'paired_game_delta':ci(x.groupby('game_id').delta.mean())}
        result['platforms'][site]={'all':metrics(g),'large_misses':{k:metrics(x) for k,x in g[g.large_miss_independent].groupby('tier_independent')},'mean_abs_projection_error':{arm:float(abs(g['mean_'+arm]-g['projection_'+arm]).mean()) for arm in arms}}
    keys_frame=pd.read_csv(root/'minutes-script-results/primary_context.csv',dtype={'package':str,'game_id':str})[['package','game_id','team_key']].drop_duplicates().rename(columns={'team_key':'team'})
    primary=f.merge(keys_frame,on=['package','game_id','team'],validate='many_to_one');result['primary_coverage_delta']=ci(primary.groupby('game_id').delta.mean());result['primary_coverage']={arm:float(primary['covered_'+arm].mean()) for arm in arms}
    reports={}
    for arm in arms:
        r=[x for p in out.glob('*_'+arm+'_report.json') for x in json.loads(p.read_text())['reports']]
        residual=[abs(v) for x in r for v in (x.get('calibration',{}).get('residual') or [])]
        reports[arm]={'max_absolute_team_mean_residual':max(residual,default=None),'game_reports':len(r)}
    result['calibration']=reports
    f.to_csv(out/'paired_fantasy_rows.csv',index=False);(out/'fantasy_summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':run(sys.argv[1])
