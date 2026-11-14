"""Expanding-date development CV. No observed test labels enter trial sampler."""
import argparse,hashlib,io,itertools,json,sys,zipfile
from pathlib import Path
import numpy as np,pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_nba_shared_bench_offline import draw_bench_minutes
from simmah_nba_coupled_minutes_offline import redistribute
from simmah_nba_pregame import PregameEngine
from simmah_nba_engine import EventRates
from scripts.expand_minutes_evidence_offline import player_key

def tier(m):return 'bench' if m<18 else 'rotation' if m<28 else 'core'
def fit(train):
    if train.empty:raise ValueError('Earlier dates required')
    teams=[]
    for (_,team),g in train.groupby(['game_id','team_key']):
        g=g.sort_values(['projected_minutes','name_key'],ascending=[False,True]);d=g.delta.to_numpy();top=np.arange(len(g))<7
        state='blowout' if g.blowout_proxy.iloc[0] else 'tight' if g.competitive_proxy.iloc[0] else 'neutral'
        # Matched-player transfer proxy, not reconstructed substitution stints.
        budget=min(max(0.,-d[top].sum()),max(0.,d[~top].sum())) if state=='blowout' else min(max(0.,d[top].sum()),max(0.,-d[~top].sum())) if state=='tight' else 0.
        teams.append((g.game_id.iloc[0],state,budget))
    t=pd.DataFrame(teams,columns=['game','state','budget']);game=t.drop_duplicates('game')
    probs={s:float(((game.state==s).sum()+.5)/(len(game)+1.5)) for s in ['blowout','tight','neutral']}
    sizes={s:float(t.loc[t.state==s,'budget'].median()) if (t.state==s).any() else 0. for s in ['blowout','tight']}
    foul={}
    for name in ['bench','rotation','core']:
        g=train[train.projected_minutes.map(tier)==name];valid=g[g.foul_ledger_verified]
        hits=valid[valid.foul_threshold_proxy]
        foul[name]={'probability':float((len(hits)+.5)/(len(valid)+1)) if len(valid) else 0.,'cut':float(np.maximum(0.,-hits.delta).median()) if len(hits) else 0.,'n':len(valid)}
    return {'max_train_date':str(train.date.max()),'train_games':int(train.game_id.nunique()),'probabilities':probs,'transfer_medians':sizes,'foul':foul}

def sampler(model,arm):
    def draw(means,n,seed):
        v=draw_bench_minutes(means,n,seed,shared=arm=='shared')
        if arm!='coupled':return v
        seq=seed if isinstance(seed,np.random.SeedSequence) else np.random.SeedSequence(seed)
        entropy=np.asarray(seq.entropy).reshape(-1).astype(int).tolist()
        # Engine entropy [seed,game_index,team,731]: same script uniform across teams.
        shared_entropy=entropy[:2]+[991] if len(entropy)>=4 else entropy+[991]
        u=np.random.default_rng(np.random.SeedSequence(shared_entropy)).random(n)
        rng=np.random.default_rng(np.random.SeedSequence(entropy+[992]));p=model['probabilities'];b=model['transfer_medians']
        for k in range(n):
            state='blowout' if u[k]<p['blowout'] else 'tight' if u[k]<p['blowout']+p['tight'] else 'neutral'
            cuts={i:model['foul'][tier(m)]['cut'] for i,m in enumerate(means) if m>0 and rng.random()<model['foul'][tier(m)]['probability']}
            v[k],_=redistribute(v[k],means,state=state,transfer_budget=b.get(state,0.),foul_cuts=cuts)
        return v
    return draw

def load_archive(path):
    with zipfile.ZipFile(path) as z:raw=z.read('original_build.zip') if 'original_build.zip' in z.namelist() else path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        manifest=json.loads(z.read('manifest.json'))
        for name,entry in manifest['files'].items():
            if hashlib.sha256(z.read(name)).hexdigest()!=entry['sha256']:raise ValueError('Frozen archive hash mismatch')
        meta=json.loads(z.read('inputs/player_pool.json'));pool=pd.DataFrame(meta['rows']);pool.attrs=meta['attrs'];contest=json.loads(z.read('inputs/contest.json'))
        markets=json.loads(z.read('inputs/markets.json'));rates=EventRates(**json.loads(z.read('inputs/engine.json'))['rates'])
    return pool,contest,markets,rates

def run(root,trials):
    root=Path(root);out=root/'minutes-coupled-cv';out.mkdir(exist_ok=True)
    primary=pd.read_csv(root/'minutes-script-results/primary_context.csv',dtype={'game_id':str,'package':str});primary=primary[primary.overtimes==0]
    f=pd.read_csv(root/'minutes-script-results/all_forecasts_context.csv',dtype={'game_id':str,'package':str});f=f[f.overtimes==0]
    dates=sorted(primary.date.unique());models={}
    for date in dates[1:]:
        model=fit(primary[primary.date<date]);assert model['max_train_date']<date;models[date]=model
    (out/'folds.json').write_text(json.dumps(models,indent=2))
    minutes=[];pairs=[]
    for path in sorted((root/'minutes-expanded-evidence').glob('*.zip')):
        pool,contest,markets,rates=load_archive(path);date=contest['date'];package=str(contest['id'])
        if date not in models:continue
        obs=f[f.package==package].copy();obs['_key']=[player_key(n,t) for n,t in zip(obs.name,obs.team)]
        engine=PregameEngine(pool,markets,rates,platform=contest['platform'],parallel=False)
        for gi,(_,groups) in enumerate(engine.games):
            for ti,(ids,means,_) in enumerate(groups):
                keyed={player_key(pool.iloc[i].Name,pool.iloc[i].Team):k for k,i in enumerate(ids)};g=obs[obs._key.isin(keyed)]
                if g.empty:continue
                arrays={arm:sampler(models[date],arm)(means,trials,np.random.SeedSequence([2100,gi,ti,731])) for arm in ['independent','shared','coupled']}
                for x in arrays.values():assert np.allclose(x.sum(1),240)
                matched=[]
                for r in g.itertuples():
                    j=keyed[r._asdict()['_key']] if '_key' in r._asdict() else keyed[player_key(r.name,r.team)]
                    item={'package':package,'platform':contest['platform'],'date':date,'game_id':r.game_id,'team':r.team_key,'name':r.name_key,'tier':r.tier,'large_miss':abs(r.delta)>5,'actual_minutes':r.actual_minutes,'physical_mean':float(means[j]),'primary':bool(((primary.package==package)&(primary.game_id==r.game_id)&(primary.team_key==r.team_key)).any())}
                    for arm,x in arrays.items():
                        lo,hi=np.quantile(x[:,j],[.1,.9]);item[arm+'_covered']=bool(lo<=r.actual_minutes<=hi);item[arm+'_abs_error']=float(abs(x[:,j].mean()-r.actual_minutes))
                    minutes.append(item);matched.append((r,j))
                bench=[(r,j) for r,j in matched if 0<means[j]<18]
                for (a,i),(b,j) in itertools.combinations(bench,2):
                    row={'package':package,'game_id':a.game_id,'primary':minutes[-1]['primary'],'event':bool(a.actual_minutes>means[i]+5 and b.actual_minutes>means[j]+5)}
                    for arm,x in arrays.items():
                        p=(((x[:,i]>means[i]+5)&(x[:,j]>means[j]+5)).sum()+.5)/(trials+1);row[arm+'_probability']=p;row[arm+'_brier']=(p-row['event'])**2
                    pairs.append(row)
        pd.DataFrame(minutes).to_csv(out/'minutes.csv',index=False);pd.DataFrame(pairs).to_csv(out/'pairs.csv',index=False)
        print('checkpoint',package,flush=True)
    m=pd.DataFrame(minutes);q=pd.DataFrame(pairs);mp=m[m.primary];qp=q[q.primary]
    result={'offline_only':True,'trials':trials,'first_date_training_only':dates[0],'evaluation_dates':dates[1:],'primary_games':mp.game_id.nunique(),'primary_pairs':len(qp),'observed_cospike':float(qp.event.mean()),'minute_coverage':{},'pair_predictions':{},'fantasy_coverage':'Not measured by minute-only sampler; full engine replay required','status':'Chronological development CV, not untouched external holdout; no promotion'}
    for arm in ['independent','shared','coupled']:
        result['minute_coverage'][arm]={'all':float(mp[arm+'_covered'].mean()),'mae':float(mp[arm+'_abs_error'].mean()),'large_misses':{k:float(x[arm+'_covered'].mean()) for k,x in mp[mp.large_miss].groupby('tier')}}
        result['pair_predictions'][arm]={'mean':float(qp[arm+'_probability'].mean()),'brier_game_weighted':float(qp.groupby('game_id')[arm+'_brier'].mean().mean())}
    delta=qp.groupby('game_id').apply(lambda g:float((g.coupled_brier-g.independent_brier).mean()),include_groups=False).to_numpy();rng=np.random.default_rng(8001)
    result['coupled_minus_independent_brier_ci95']=np.quantile(delta[rng.integers(len(delta),size=(2000,len(delta)))].mean(1),[.025,.975]).tolist()
    (out/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('--trials',type=int,default=2000);a=p.parse_args();run(a.root,a.trials)
