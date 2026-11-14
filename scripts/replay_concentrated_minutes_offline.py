"""Frozen pre-Nov6 candidate; paired reuse of29 development-verification games."""
import argparse,itertools,json,sys,time
from pathlib import Path
from unittest.mock import patch
import numpy as np,pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.fit_coupled_minutes_offline import load_archive,sampler,tier
from scripts.expand_minutes_evidence_offline import player_key,team_key
from simmah_nba_shared_bench_offline import draw_bench_minutes
from simmah_nba_concentrated_minutes_offline import redistribute_concentrated,compile_patterns
from simmah_nba_pregame import PregameEngine

def draw_concentrated(means,n,seed,model,patterns,names,team):
    v=draw_bench_minutes(means,n,seed,shared=False);seq=seed if isinstance(seed,np.random.SeedSequence) else np.random.SeedSequence(seed);ent=np.asarray(seq.entropy).reshape(-1).astype(int).tolist()
    u=np.random.default_rng(np.random.SeedSequence(ent[:2]+[991])).random(n);rng=np.random.default_rng(np.random.SeedSequence(ent+[992]));route=np.random.default_rng(np.random.SeedSequence(ent+[993]));p=model['probabilities']
    for k in range(n):
        state='blowout' if u[k]<p['blowout'] else 'tight' if u[k]<p['blowout']+p['tight'] else 'neutral'
        cuts={i:model['foul'][tier(m)]['cut'] for i,m in enumerate(means) if m>0 and rng.random()<model['foul'][tier(m)]['probability']}
        v[k],_=redistribute_concentrated(v[k],means,names,team,patterns,int(route.integers(2**32)),state=state,transfer_budget=model['transfer_medians'].get(state,0.),foul_cuts=cuts)
    return v

def engine_sampler(engine,model,patterns,arm):
    def draw(means,n,seed):
        if arm=='diffuse_fixed':return sampler(model,'coupled')(means,n,seed)
        ent=np.asarray(seed.entropy).reshape(-1).astype(int);gi,ti=int(ent[1]),int(ent[2]);ids=engine.games[gi][1][ti][0];names=[str(engine.pool.iloc[i].Name) for i in ids]+['__inactive_'+str(i) for i in range(len(means)-len(ids))];team=team_key(engine.pool.iloc[ids[0]].Team)
        return draw_concentrated(means,n,seed,model,patterns,names,team)
    return draw

def run(root,package_filter=None,minute_only=False):
    root=Path(root);out=root/'concentrated-recipient-cv';out.mkdir(exist_ok=True)
    # Freeze first fold only: none of29 evaluation games train script rates/magnitudes.
    model=json.loads((root/'minutes-coupled-cv/folds.json').read_text())['2026-11-06'];assert model['max_train_date']<'2026-11-06'
    patterns=compile_patterns(json.loads((root/'earlier-recipient-results/recipient_patterns.json').read_text()))
    f=pd.read_csv(root/'minutes-script-results/all_forecasts_context.csv',dtype={'game_id':str,'package':str,'player_id':str});f=f[(f.overtimes==0)&(f.date>='2026-11-06')]
    primary=pd.read_csv(root/'minutes-script-results/primary_context.csv',dtype={'game_id':str,'package':str})
    for path in sorted((root/'minutes-expanded-evidence').glob('*.zip')):
        pool,c,markets,rates=load_archive(path);package=str(c['id'])
        if c['date']<'2026-11-06' or (package_filter and package!=package_filter):continue
        pool.attrs['nba_variable_minutes']=True;pool.attrs['nba_wider_minutes']=True;obs=f[f.package==package];index={str(p):i for i,p in enumerate(pool['Player ID'])}
        for arm in ['diffuse_fixed','concentrated']:
            target=out/(package+'_'+arm+'_fp.csv')
            if not minute_only and target.exists():continue
            engine=PregameEngine(pool,markets,rates,platform=c['platform'],parallel=False);draw=engine_sampler(engine,model,patterns,arm);start=time.perf_counter()
            if minute_only:
                rows=[];pairs=[]
                for gi,(_,groups) in enumerate(engine.games):
                    for ti,(ids,means,_) in enumerate(groups):
                        keys={player_key(pool.iloc[i].Name,pool.iloc[i].Team):k for k,i in enumerate(ids)};g=obs[[player_key(r.name,r.team) in keys for r in obs.itertuples()]]
                        if g.empty:continue
                        size=max(len(a[0]) for a in groups);padded=np.zeros(size);padded[:len(means)]=means;x=draw(padded,2000,np.random.SeedSequence([2100,gi,ti,731]));matched=[]
                        for r in g.itertuples():
                            j=keys[player_key(r.name,r.team)];isprimary=bool(((primary.package==package)&(primary.game_id==r.game_id)&(primary.team_key==r.team_key)).any());lo,hi=np.quantile(x[:,j],[.1,.9]);rows.append({'package':package,'game_id':r.game_id,'name':r.name_key,'primary':isprimary,'covered':bool(lo<=r.actual_minutes<=hi),'tier':r.tier});matched.append((r,j,isprimary))
                        for (a,i,pri),(b,j,_) in itertools.combinations([(r,j,p) for r,j,p in matched if 0<means[j]<18],2):
                            prob=(((x[:,i]>means[i]+5)&(x[:,j]>means[j]+5)).sum()+.5)/2001;event=bool(a.actual_minutes>means[i]+5 and b.actual_minutes>means[j]+5);pairs.append({'package':package,'game_id':a.game_id,'primary':pri,'event':event,'probability':prob,'brier':(prob-event)**2})
                pd.DataFrame(rows).to_csv(out/(package+'_'+arm+'_minutes.csv'),index=False);pd.DataFrame(pairs).to_csv(out/(package+'_'+arm+'_pairs.csv'),index=False)
                continue
            with patch('simmah_nba_pregame.draw_wider_minutes',draw):engine(1024,83);x=engine(2000,2100)
            rows=[]
            for r in obs.itertuples():
                i=index[str(r.player_id)];lo,hi=np.quantile(x[:,i],[.1,.9]);rows.append({'package':package,'date':c['date'],'platform':c['platform'],'game_id':r.game_id,'team':r.team_key,'name':r.name_key,'tier':r.tier,'large_miss':abs(r.delta)>5,'actual':r.actual,'p10':float(lo),'p90':float(hi),'covered':bool(lo<=r.actual<=hi),'mean':float(x[:,i].mean()),'projection':r.source_projection})
            pd.DataFrame(rows).to_csv(target,index=False);(out/(package+'_'+arm+'_report.json')).write_text(json.dumps({'seconds':time.perf_counter()-start,'reports':engine.last_report},default=str));print(package,arm,round(time.perf_counter()-start,1),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('--package');p.add_argument('--minute-only',action='store_true');a=p.parse_args();run(a.root,a.package,a.minute_only)
