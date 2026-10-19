"""Separate-contest salary/position ownership pilot; no live app integration."""
import argparse,json,sys,hashlib
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from simmah_contest_history import parse_lineups,verified_fanduel_mvp_first,name_key

POSITIONS=['QB','RB','WR','TE','K','DST']

def load(path):
    frame=pd.read_csv(path,low_memory=False)
    # Published points establish MVP slot identity only; never model predictors.
    scored=frame[pd.to_numeric(frame.Points,errors='coerce').notna()]
    lineups=[r for r in parse_lineups(scored) if len(r)==6]
    lineups=verified_fanduel_mvp_first(frame,lineups)
    meta=frame.loc[frame.Player.notna(),['Player','Roster Position','Salary']].copy()
    meta['key']=meta.Player.map(name_key)
    if meta.groupby('key').Salary.nunique().max()>1:raise ValueError('Conflicting salaries')
    meta=meta.drop_duplicates('key').set_index('key')
    meta['salary']=pd.to_numeric(meta.Salary,errors='raise')
    meta=meta[meta.salary.gt(0)].copy()
    meta['position']=meta['Roster Position'].replace({'D':'DST','DEF':'DST','FB':'RB'})
    if not meta.position.isin(POSITIONS).all():raise ValueError('Unknown position')
    valid=[r for r in lineups if all(name_key(n) in meta.index for _,n in r)]
    if len(valid)!=len(lineups):raise ValueError('Incomplete same-contest metadata')
    mvp=Counter(name_key(r[0][1]) for r in valid)
    flex=Counter(name_key(n) for r in valid for _,n in r[1:])
    meta['actual_mvp']=[mvp[k]/len(valid) for k in meta.index]
    meta['actual_flex']=[flex[k]/len(valid) for k in meta.index]
    assert abs(meta.actual_mvp.sum()-1)<1e-8 and abs(meta.actual_flex.sum()-5)<1e-8
    return meta,len(valid)

def features(pool):
    salary=pool.salary.to_numpy(float)
    return np.column_stack([np.ones(len(pool)),np.log(salary/np.median(salary)),
        pd.Series(salary).rank(pct=True).to_numpy(),
        *[pool.position.eq(p).to_numpy(float) for p in POSITIONS]])

def marginals(mvp_weights,flex_weights):
    mvp=np.asarray(mvp_weights,float);flex_weights=np.asarray(flex_weights,float)
    if len(mvp)<6 or len(mvp)!=len(flex_weights) or not np.isfinite(mvp).all() or not np.isfinite(flex_weights).all() or (mvp<=0).any() or (flex_weights<=0).any():
        raise ValueError('At least six players with finite positive weights required')
    mvp=mvp/mvp.sum()
    cap=1-mvp;weights=np.asarray(flex_weights,float)
    lo,hi=0.,1.
    while np.minimum(cap,hi*weights).sum()<5-1e-12:hi*=2
    for _ in range(100):
        mid=(lo+hi)/2
        if np.minimum(cap,mid*weights).sum()<5:lo=mid
        else:hi=mid
    flex=np.minimum(cap,hi*weights)
    assert abs(mvp.sum()-1)<1e-8 and abs(flex.sum()-5)<1e-8 and (mvp+flex<=1+1e-8).all()
    return mvp,flex

def main():
    p=argparse.ArgumentParser();p.add_argument('--train',required=True);p.add_argument('--test');p.add_argument('--predict-rw');p.add_argument('--output',required=True);a=p.parse_args()
    if bool(a.test)==bool(a.predict_rw):raise ValueError('Choose separate-contest --test or pregame --predict-rw')
    if a.test and Path(a.train).resolve()==Path(a.test).resolve():raise ValueError('Holdout must be a separate contest')
    train,ntrain=load(a.train)
    x=features(train);penalty=5*np.eye(x.shape[1]);penalty[0,0]=0
    coefficients={role:np.linalg.solve(x.T@x+penalty,x.T@np.log(train['actual_'+role].to_numpy()+1e-4)) for role in ['mvp','flex']}
    if a.predict_rw:
        from datetime import datetime,timezone
        now=datetime.now(timezone.utc)
        if now >= datetime.fromisoformat('2026-10-20T00:15:00+00:00'):
            raise ValueError('Predictions must be frozen before kickoff')
        raw=json.loads(Path(a.predict_rw).read_text())
        if {r['team']['abbr'] for r in raw}!={'WAS','SF'} or any(r['game']['dateTime'][:10]!='2026-10-19' for r in raw):
            raise ValueError('Unexpected prospective slate')
        rows=[r for r in raw if float(r.get('pts') or 0)>0 and float(r['salary'])>0]
        pool=pd.DataFrame([{'Name':r['firstName']+' '+r['lastName'],
            'salary':float(r['salary']),'position':{'FB':'RB','DEF':'DST','D':'DST'}.get(r['rotoPos'],r['rotoPos'])} for r in rows])
        xp=features(pool)
        for label,weights in [('salary_rule',(pool.salary.to_numpy()**2,pool.salary.to_numpy())),
                ('learned_salary_position',tuple(np.exp(np.clip(xp@coefficients[role],-30,30)) for role in ['mvp','flex']))]:
            mvp,flex=marginals(*weights)
            pool[label+'_mvp_pct']=100*mvp;pool[label+'_flex_pct']=100*flex
        out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
        if out.exists() or out.with_suffix('.csv').exists():raise FileExistsError('Frozen trial already exists')
        pool.to_csv(out.with_suffix('.csv'),index=False)
        report={'scope':'Prospective FD Single Game ownership pilot, no measured accuracy yet; not used in live builds.',
            'created_at':now.isoformat(),'kickoff':'2026-10-20T00:15:00+00:00',
            'training_contest':Path(a.train).stem,'training_entries':ntrain,'training_players':len(train),
            'prediction_players':len(pool),'ridge':5,'smoothing':.0001,
            'features':['intercept','log_salary_over_slate_median','salary_percentile',*POSITIONS],
            'coefficients':{k:v.tolist() for k,v in coefficients.items()},
            'sources':{Path(p).name:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in [a.train,a.predict_rw]},
            'limitations':['Only one verified complete training contest.',
                'Earlier FD standings are truncated and were rejected as a holdout.',
                'Salary/position only: no verified historical pregame projections or news.',
                'Candidate pool limited to 29 positive RotoWire players; unmatched actual players must be reported.',
                'Marginal constraints do not establish feasible joint lineups or duplicate frequencies.',
                'Actual points verify MVP ordering only and are excluded from predictors.']}
        out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return
    # No test ownership is used in fitting or parameter selection.
    test,ntest=load(a.test);xt=features(test)
    arms={
        'uniform':marginals(np.ones(len(test)),np.ones(len(test))),
        'salary_rule':marginals(test.salary.to_numpy()**2,test.salary.to_numpy()),
        'learned_salary_position':marginals(*[np.exp(np.clip(xt@coefficients[role],-30,30)) for role in ['mvp','flex']])}
    results={}
    for label,(mvp,flex) in arms.items():
        test[label+'_mvp']=mvp;test[label+'_flex']=flex
        results[label]={role+'_mae_percentage_points':float(100*np.abs(test['actual_'+role]-pred).mean()) for role,pred in [('mvp',mvp),('flex',flex),('overall',mvp+flex)] if role!='overall'}
        results[label]['overall_mae_percentage_points']=float(100*np.abs(test.actual_mvp+test.actual_flex-mvp-flex).mean())
    report={'scope':'Experimental FD Single Game separate-contest ownership pilot. Salary/position only; no archived pregame projections are assumed. No live app changes or ROI claims.',
        'training_contest':Path(a.train).stem,'training_entries':ntrain,'test_contest':Path(a.test).stem,'test_entries':ntest,
        'source_hashes':{Path(path).name:hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in [a.train,a.test]},
        'parameters':{'ridge':5,'label_smoothing':.0001,'features':['intercept','log_salary_over_slate_median','salary_percentile',*POSITIONS]},
        'metrics':results,'coefficients':{k:v.tolist() for k,v in coefficients.items()},
        'limitations':['One training game and one held-out game cannot establish generalization.',
            'Salary-only inputs omit projected points, injury opportunities and news.',
            'Player marginals do not guarantee feasible salary-constrained joint lineups.',
            'First-listed MVP identity is verified using actual points, which never enter predictors.']}
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
    # Anonymous validation rows: no player/user names, entry IDs or actual scores.
    test.drop(columns=['Player','Roster Position','Salary']).reset_index(drop=True).to_csv(out.with_suffix('.csv'),index=False)
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
