"""Frozen multi-build minute-dependence ablation and matched-minutes FP slices."""
import argparse,hashlib,io,itertools,json,re,sys,zipfile
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from simmah_nba_pregame import PregameEngine
from simmah_nba_engine import EventRates
from simmah_nba_projections import player_key
from simmah_nba_shared_bench_offline import draw_bench_minutes


def summarize_interval(frame):
    if frame.empty:return {'n':0}
    return {'n':len(frame),'games':frame.game_id.nunique(),
        'coverage80':float(((frame.actual>=frame.p10)&(frame.actual<=frame.p90)).mean()),
        'above_p90':float((frame.actual>frame.p90).mean()),
        'below_p10':float((frame.actual<frame.p10).mean()),
        'above_p99':float((frame.actual>frame.p99).mean())}


def verify_pregame_forecasts(frame):
    if frame[['package','player_id']].duplicated().any():raise ValueError('Duplicate frozen player forecast')
    for capture,opening in zip(frame.captured_at,frame.observed_opening_utc):
        a,b=pd.Timestamp(capture),pd.Timestamp(opening)
        if pd.isna(a) or pd.isna(b) or a.tzinfo is None or b.tzinfo is None:
            raise ValueError('Timezone-aware capture and opening timestamps required')
        if a>=b:raise ValueError('Forecast capture must precede observed opening')


def run(evidence,audit,output,extra_forecast=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    policy=ROOT/'data/nba_rotation_trials/shared-bench-v1-policy.json'
    config=json.loads(policy.read_text());trials=config['trials'];seed=config['evaluation_seed']
    with zipfile.ZipFile(audit) as z:
        forecast=pd.read_csv(io.BytesIO(z.read('player-forecast-audit.csv')),dtype={'package':str,'game_id':str,'player_id':str})
    if extra_forecast:
        extra=pd.read_csv(extra_forecast,dtype={'package':str,'game_id':str,'player_id':str})
        forecast=pd.concat([forecast,extra],ignore_index=True)
    # The audited source is already limited to observed pre-tip predictions.
    verify_pregame_forecasts(forecast)
    forecast['_key']=[player_key(n,t) for n,t in zip(forecast.name,forecast.team)]
    packages=[];minutes=[];pairs=[];team_snapshots=[];errors=[]
    for path in sorted(Path(evidence).rglob('*.zip')):
        with zipfile.ZipFile(path) as outer:
            payload=outer.read('original_build.zip') if 'original_build.zip' in outer.namelist() else path.read_bytes()
        with zipfile.ZipFile(io.BytesIO(payload)) as z:
            manifest=json.loads(z.read('manifest.json'))
            for name,meta in manifest['files'].items():
                if hashlib.sha256(z.read(name)).hexdigest()!=meta['sha256']:raise ValueError('Archive manifest mismatch')
            meta=json.loads(z.read('inputs/player_pool.json'));pool=pd.DataFrame(meta['rows']);pool.attrs=meta['attrs']
            contest=json.loads(z.read('inputs/contest.json'));package=str(contest['id']);platform=contest['platform']
            markets=json.loads(z.read('inputs/markets.json'));rates=EventRates(**json.loads(z.read('inputs/engine.json'))['rates'])
        observed=forecast[forecast.package==package]
        if observed.empty:continue
        try:engine=PregameEngine(pool,markets,rates,platform=platform,parallel=False)
        except ValueError as exc:
            errors.append({'package':package,'reason':str(exc)});continue
        packages.append({'package':package,'date':contest['date'],'platform':platform,'source_sha256':hashlib.sha256(payload).hexdigest(),
            'original_variable_minutes':bool(pool.attrs.get('nba_variable_minutes')),'original_wider_minutes':bool(pool.attrs.get('nba_wider_minutes')),
            'reference':'current production variable+wider law in both arms; no full-game FP replay',
            'rotation_reconciliation':engine.rotation_reconciliation})
        for gi,(market,groups) in enumerate(engine.games):
            for ti,(ids,means,_) in enumerate(groups):
                keyed={player_key(pool.iloc[i].Name,pool.iloc[i].Team):k for k,i in enumerate(ids)}
                obs=observed[observed['_key'].isin(keyed)].copy()
                if obs.empty:continue
                if obs.game_id.nunique()!=1:raise ValueError('Ambiguous game join')
                game=str(obs.game_id.iloc[0]);team=player_key('',pool.iloc[ids[0]].Team)[1]
                if obs.overtimes.max()>0:
                    errors.append({'package':package,'game':game,'team':team,'reason':'actual OT; regulation-only minute test withheld'});continue
                stamp=pd.to_datetime(obs.captured_at,utc=True).max().isoformat()
                team_snapshots.append({'package':package,'game_id':game,'team':team,'capture':stamp})
                arrays={label:draw_bench_minutes(means,trials,np.random.SeedSequence([seed,gi,ti,731]),shared=shared)
                    for label,shared in [('independent',False),('shared',True)]}
                for label,x in arrays.items():
                    if not np.allclose(x.sum(1),240,atol=1e-8,rtol=0):raise ValueError('Minute conservation failed')
                obs=obs.set_index('_key')
                matched=[]
                for pk,k in keyed.items():
                    if pk not in obs.index:continue
                    row=obs.loc[[pk]]
                    if len(row)!=1:raise ValueError('Duplicate pregame player observation')
                    row=row.iloc[0];truth=float(row.actual_minutes)
                    matched.append((pk,k,truth))
                    item={'package':package,'platform':platform,'game_id':game,'team':team,'name':row['name'],
                        'provider_mean':float(row.projected_minutes),'physical_mean':float(means[k]),'actual_minutes':truth}
                    for label,x in arrays.items():
                        low,high=np.quantile(x[:,k],[.1,.9]);item[label+'_covered80']=bool(low<=truth<=high)
                        item[label+'_mean']=float(x[:,k].mean());item[label+'_variance']=float(x[:,k].var())
                    minutes.append(item)
                bench=[(pk,k,t) for pk,k,t in matched if 0<means[k]<18]
                for (pa,i,ta),(pb,j,tb) in itertools.combinations(bench,2):
                    row={'package':package,'platform':platform,'game_id':game,'team':team,'player_a':pa[0],'player_b':pb[0],
                        'event':bool(ta>means[i]+5 and tb>means[j]+5)}
                    for label,x in arrays.items():
                        hits=int(((x[:,i]>means[i]+5)&(x[:,j]>means[j]+5)).sum());prob=(hits+.5)/(trials+1)
                        y=float(row['event']);row[label+'_probability']=prob;row[label+'_brier']=(prob-y)**2
                        row[label+'_logloss']=-y*np.log(prob)-(1-y)*np.log1p(-prob)
                    pairs.append(row)
        # Per-package checkpoints make this robust to interrupted environments.
        pd.DataFrame(minutes).to_csv(output/'minute_rows.csv',index=False)
        pd.DataFrame(pairs).to_csv(output/'joint_bench_pairs.csv',index=False)
    minute=pd.DataFrame(minutes);pair=pd.DataFrame(pairs)
    if minute.empty or pair.empty:raise ValueError('No evaluable frozen rotations/pairs')
    choices=pd.DataFrame(team_snapshots).sort_values(['capture','package']).drop_duplicates(['game_id','team'],keep='last')
    choice=set(zip(choices.package,choices.game_id,choices.team))
    minute['primary']=[(r.package,r.game_id,r.team) in choice for r in minute.itertuples()]
    pair['primary']=[(r.package,r.game_id,r.team) in choice for r in pair.itertuples()]
    minute.to_csv(output/'minute_rows.csv',index=False);pair.to_csv(output/'joint_bench_pairs.csv',index=False)
    primary=pair[pair.primary];grouped=primary.groupby('game_id')[[x+'_'+m for x in ['independent','shared'] for m in ['brier','logloss']]].mean()
    rng=np.random.default_rng(2100731);bootstrap={}
    for metric in ['brier','logloss']:
        delta=(grouped['shared_'+metric]-grouped['independent_'+metric]).to_numpy();samples=delta[rng.integers(len(delta),size=(2000,len(delta)))].mean(1)
        bootstrap[metric]={'delta_shared_minus_independent':float(delta.mean()),'game_cluster_bootstrap95':np.quantile(samples,[.025,.975]).tolist()}
    m=minute[minute.primary];marginal={arm:{'coverage80':float(m[arm+'_covered80'].mean()),'mean_absolute_drift':float(abs(m[arm+'_mean']-m.physical_mean).mean())} for arm in ['independent','shared']}
    slices={}
    for platform in sorted(forecast.platform.unique()):
        f=forecast[(forecast.platform==platform)&(forecast.overtimes==0)].copy();f['minute_error']=(f.actual_minutes-f.projected_minutes).abs()
        groups={'all_nonOT':f,'minutes_within2':f[f.minute_error<=2],'minutes_miss_over5':f[f.minute_error>5],
            'starter_minutes_within2':f[(f.projected_minutes>=28)&(f.minute_error<=2)],
            'rotation_minutes_within2':f[(f.projected_minutes>=18)&(f.projected_minutes<28)&(f.minute_error<=2)],
            'bench_minutes_within2':f[(f.projected_minutes<18)&(f.minute_error<=2)]}
        slices[platform]={name:summarize_interval(frame) for name,frame in groups.items()}
    result={'policy':config,'policy_sha256':hashlib.sha256(policy.read_bytes()).hexdigest(),
        'source_audit_sha256':hashlib.sha256(Path(audit).read_bytes()).hexdigest(),
        'extra_forecast_sha256':hashlib.sha256(Path(extra_forecast).read_bytes()).hexdigest() if extra_forecast else None,'live_enabled':False,
        'packages':packages,'omissions':errors,'physical_games_with_pairs':len(grouped),'primary_pairs':len(primary),'observed_joint_tail_rate':float(primary.event.mean()),
        'mean_predicted_joint_tail_probability':{arm:float(primary[arm+'_probability'].mean()) for arm in ['independent','shared']},
        'paired_game_level_scores':bootstrap,'minute_marginals_primary':marginal,
        'site_joint_scores':{site:{'pairs':len(f),'brier_independent':float(f.independent_brier.mean()),'brier_shared':float(f.shared_brier.mean()),'observed_rate':float(f.event.mean())} for site,f in pair.groupby('platform')},
        'saved_FP_slices':slices,
        'limitations':['Development snapshots, not fresh holdouts; DK/FD snapshots deduplicated for primary game-cluster comparison',
            'Dependence-only minute sampler ablation; no game-state conditioned substitutions, foul engine, full-game scoring or portfolio replay',
            'Matched-minute FP slices are diagnostic controls, not direct identification of latent per-minute rate variance; archived model versions vary',
            'Actual overtime excluded rather than converted to invented regulation minutes; missing players remain unmatched',
            'No parameters trained or selected after observing this replay; primary joint log losses use Jeffreys smoothing (hits+.5)/(trials+1)',
            'No production imports the offline module; PR77 and live settings remain untouched']}
    (output/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k not in ['packages','omissions']},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('evidence');p.add_argument('audit');p.add_argument('output');p.add_argument('--extra-forecast');a=p.parse_args();run(a.evidence,a.audit,a.output,a.extra_forecast)
