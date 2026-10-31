"""Paired matchup ablation; actual outcomes are read only after simulations."""
import argparse,json,sys,hashlib,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from simmah_matchups import matchup_inputs,dated_history
from simmah_simulation_store import prepare_simulations
from simmah_weather import team_key

parser=argparse.ArgumentParser()
for name in ['players','standings','schedule','output','cache_root']:
    parser.add_argument('--'+name.replace('_','-'),required=True)
parser.add_argument('--history',nargs='+',required=True)
parser.add_argument('--slate',default='2026-10-18')
a=parser.parse_args()
pool=pd.read_csv(a.players);schedule=pd.read_csv(a.schedule,low_memory=False)
history=pd.concat([pd.read_csv(p,low_memory=False) for p in a.history],ignore_index=True)
# The selected salary slate is October 18, 2026. Resolve actual schedule pairs;
# no final scores, odds, or postgame fields enter model inputs.
schedule['day']=pd.to_datetime(schedule.gameday,errors='coerce')
games=schedule[schedule.day.eq(pd.Timestamp(a.slate))]
for i,row in pool.iterrows():
    team,opp=team_key(row.Team),team_key(row.Opponent)
    matching=games[((games.away_team.map(team_key)==team)&(games.home_team.map(team_key)==opp))|((games.home_team.map(team_key)==team)&(games.away_team.map(team_key)==opp))]
    if len(matching)!=1:raise ValueError('Unverified game '+team+' '+opp)
    g=matching.iloc[0]
    kickoff=pd.Timestamp(str(g.gameday)+' '+str(g.gametime),tz='America/New_York').tz_convert('UTC')
    pool.loc[i,'Weather Kickoff']=kickoff.isoformat()
cutoff=pool['Weather Kickoff'].min()
prior=dated_history(history,schedule,cutoff)
assert not prior.empty
# Freeze the same role estimates in both arms, excluding the entire target day.
def key(name):return ''.join(c for c in str(name).lower() if c.isalnum())
index={k:v for k,v in prior.groupby(prior.player_display_name.map(key))}
fields={'carries':'carries','targets':'targets','receptions':'receptions','rush_yards':'rushing_yards','rec_yards':'receiving_yards','rush_tds':'rushing_tds','rec_tds':'receiving_tds','pass_attempts':'attempts','completions':'completions','pass_yards':'passing_yards','pass_tds':'passing_tds','interceptions':'passing_interceptions'}
roles={}
for row in pool.itertuples():
    h=index.get(key(row.Name))
    if h is not None and row.Position in {'QB','RB','WR','TE','K'}:
        h=h.sort_values(['season','week']).tail(24)
        roles[row.Name]={out:float(pd.to_numeric(h[col],errors='coerce').fillna(0).clip(lower=0).mean()) for out,col in fields.items()}
additions,context=matchup_inputs(pool,history,schedule)
with_matchup={name:dict(v) for name,v in roles.items()}
for name,v in additions.items():with_matchup.setdefault(name,{}).update(v)
out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
snapshot={'players':pool[['Name','Team','Opponent','Position','Projection','Weather Kickoff']].to_dict('records'), 'baseline_roles':roles,'matchup_roles':with_matchup,'weather':{},'evaluation_seed':530001,'construction_seed':530002}
out.with_name(out.stem+'-inputs.json').write_text(json.dumps(snapshot,indent=2)+'\n')
frames={}; metadata={}; seed_frames={}
for label,r in [('baseline',roles),('matchup',with_matchup)]:
    print('Preparing '+label,flush=True)
    last=[-1]
    def progress(f,t):
        step=int(f*10)
        if step>last[0]:print(label,round(f*100),t,flush=True);last[0]=step
    b=prepare_simulations(pool,r,'FanDuel',a.cache_root,count=10000,weather_by_team={},progress=progress)
    seed_frames[label]={'evaluation':b['evaluation'],'construction':b['construction']}
    frames[label]=pd.concat(list(seed_frames[label].values()),ignore_index=True);metadata[label]=b['metadata']['key']
# Outcomes first accessed here, after both arms have been fitted and simulated.
actual=pd.read_csv(a.standings,low_memory=False)
actual=actual[actual.Player.notna()&actual.FPTS.notna()].copy()
actual['Name']=actual.Player.str.replace(r' \(\d+-\d+\)$','',regex=True)
assert actual.groupby('Name').FPTS.nunique().max()<=1
actual=actual.drop_duplicates('Name').set_index('Name').FPTS
matched=pool[pool.Name.isin(actual.index)].copy()
rows=[]
for row in matched.itertuples():
    y=float(actual[row.Name]);entry={'Name':row.Name,'Position':row.Position,'Team':row.Team,'Projection':row.Projection,'Actual':y}
    for label,frame in frames.items():
        x=frame[row.Name].to_numpy(dtype=float);s=np.sort(x);n=len(s)
        # Empirical CRPS: E|X-y| - 1/2 E|X-X'|.
        crps=np.abs(x-y).mean()-np.dot(2*np.arange(1,n+1)-n-1,s)/(n*n)
        lo,hi=np.quantile(x,[.1,.9])
        entry.update({label+'_mean':float(x.mean()),label+'_mae':float(abs(x.mean()-y)),label+'_crps':float(crps),label+'_coverage':bool(lo<=y<=hi)})
    rows.append(entry)
detail=pd.DataFrame(rows)
def summary(d):
    return {label:{'mean_abs_error':float(d[label+'_mae'].mean()),'crps':float(d[label+'_crps'].mean()),'p10_p90_coverage':float(d[label+'_coverage'].mean())} for label in frames}
report={'scope':'Single completed FD full slate paired ablation, not a multi-slate holdout or portfolio profit backtest. Neutral weather in both arms; common pregame-only roles reconstructed from current historical files. As-of publication timestamps unavailable. Target-day stats excluded. No parameter tuning on outcomes.', 'slate':a.slate,'players':len(pool),'matched_actuals':len(detail),'unmatched_players':pool.loc[~pool.Name.isin(actual.index),'Name'].tolist(),'outcomes_per_arm':20000,'independent_streams_per_arm':2,'history_through':str(prior._date.max().date()),'role_matches':len(roles),'matchups_applied':sum(bool(v) for v in additions.values()),'context_status':context.Status.value_counts().to_dict(),'overall':summary(detail),'by_position':{pos:summary(d) for pos,d in detail.groupby('Position')},'preparation_keys':metadata,'sources':{str(p):hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in [a.players,a.schedule,*a.history]},'crps_improved_players':int((detail.matchup_crps<detail.baseline_crps).sum())}
# Paired game-cluster bootstrap: players in a game share outcomes.
team_pairs={r.Team:'-'.join(sorted([r.Team,r.Opponent])) for r in pool.itertuples()}
detail['game']=detail.Team.map(team_pairs)
clusters=detail.assign(delta=detail.matchup_crps-detail.baseline_crps).groupby('game').delta.agg(['sum','count'])
rng=np.random.default_rng(80719)
samples=rng.integers(0,len(clusters),size=(10000,len(clusters)))
means=clusters['sum'].to_numpy()[samples].sum(axis=1)/clusters['count'].to_numpy()[samples].sum(axis=1)
report['projected_8_plus']={'players':int(detail.Projection.ge(8).sum()),'metrics':summary(detail[detail.Projection.ge(8)])}
report['crps_delta_game_cluster_bootstrap_95pct']=np.quantile(means,[.025,.975]).tolist()
report['crps_delta_matchup_minus_baseline']=float((detail.matchup_crps-detail.baseline_crps).mean())
report['independent_stream_crps']={}
for stream in ['evaluation','construction']:
    report['independent_stream_crps'][stream]={}
    for label in seed_frames:
        vals=[]
        for row in matched.itertuples():
            x=seed_frames[label][stream][row.Name].to_numpy(dtype=float);s=np.sort(x);n=len(s)
            vals.append(float(np.abs(x-float(actual[row.Name])).mean()-np.dot(2*np.arange(1,n+1)-n-1,s)/(n*n)))
        report['independent_stream_crps'][stream][label]=float(np.mean(vals))
out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n');detail.to_csv(out.with_suffix('.csv'),index=False);context.to_csv(out.with_name(out.stem+'-context.csv'),index=False)
print(json.dumps(report,indent=2),flush=True)
