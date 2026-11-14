"""One frozen-candidate verification summary, not a tuning objective."""
import json,sys
from pathlib import Path
import numpy as np,pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.summarize_coupled_minutes_fp_offline import ci

def read(paths):return pd.concat([pd.read_csv(p,dtype={'game_id':str,'package':str}) for p in paths],ignore_index=True)
def run(root):
    root=Path(root);out=root/'concentrated-recipient-cv';original=root/'minutes-coupled-cv';arms={'independent':read(original.glob('*_independent_fp.csv')),**{arm:read(out.glob('*_'+arm+'_fp.csv')) for arm in ['diffuse_fixed','concentrated']}}
    keys=['package','game_id','team','name'];base=arms['independent'];joined=base.copy()
    if base.duplicated(keys).any():raise ValueError('Duplicate baseline')
    for arm in ['diffuse_fixed','concentrated']:
        x=arms[arm];joined=joined.merge(x[keys+['covered','p10','p90','mean']].rename(columns={c:arm+'_'+c for c in ['covered','p10','p90','mean']}),on=keys,validate='one_to_one')
        if len(joined)!=len(base) or len(x)!=len(base):raise ValueError('Incomplete paired cohort')
    joined['delta']=joined.concentrated_covered.astype(float)-joined.covered.astype(float)
    result={'live_enabled':False,'builds':joined.package.nunique(),'games':joined.game_id.nunique(),'rows':len(joined),'platforms':{},'pair_metrics':{},'decision':'not assessed until all joint metrics reviewed; no automatic promotion','scope':'29 previously inspected development-verification games; no model fit uses their outcomes in this candidate'}
    def metrics(x):
        return {'n':len(x),'independent':float(x.covered.mean()),'diffuse_fixed':float(x.diffuse_fixed_covered.mean()),'concentrated':float(x.concentrated_covered.mean()),'concentrated_minus_independent_game_delta':ci(x.groupby('game_id').delta.mean())}
    for platform,g in joined.groupby('platform'):
        result['platforms'][platform]={'all':metrics(g),'large_miss_tiers':{k:metrics(x) for k,x in g[g.large_miss].groupby('tier')},'mean_projection_mae':{'independent':float(abs(g['mean']-g.projection).mean()),**{arm:float(abs(g[arm+'_mean']-g.projection).mean()) for arm in ['diffuse_fixed','concentrated']}}}
    for arm in ['diffuse_fixed','concentrated']:
        p=read(out.glob('*_'+arm+'_pairs.csv'));p=p[p.primary];result['pair_metrics'][arm]={'n':len(p),'games':p.game_id.nunique(),'observed':float(p.event.mean()),'predicted':float(p.probability.mean()),'game_weighted_brier':float(p.groupby('game_id').brier.mean().mean())}
        m=read(out.glob('*_'+arm+'_minutes.csv'));m=m[m.primary];result.setdefault('minute_coverage',{})[arm]=float(m.covered.mean())
    # Same physical comparison cohort and earlier reference arms.
    p=pd.read_csv(original/'pairs.csv',dtype={'game_id':str});p=p[p.primary];result['pair_metrics']['independent']={'n':len(p),'games':p.game_id.nunique(),'observed':float(p.event.mean()),'predicted':float(p.independent_probability.mean()),'game_weighted_brier':float(p.groupby('game_id').independent_brier.mean().mean())}
    reports={}
    for arm in ['diffuse_fixed','concentrated']:
        r=[x for p in out.glob('*_'+arm+'_report.json') for x in json.loads(p.read_text())['reports']];res=[abs(v) for x in r for v in (x.get('calibration',{}).get('residual') or [])]
        reports[arm]={'max_absolute_team_residual':max(res,default=None),'reports':len(r)}
    result['calibration']=reports
    joined.to_csv(out/'matched_fantasy_rows.csv',index=False);(out/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':run(sys.argv[1])
