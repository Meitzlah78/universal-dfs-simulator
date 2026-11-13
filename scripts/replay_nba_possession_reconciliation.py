"""Full-possession diagnostic replay; fixed seeds and model parameters."""
import json,sys
from pathlib import Path
from dataclasses import replace
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from audit_nba_clock import load,observed
from audit_nba_hazards import observe_hazards,fit_hazards
from replay_nba_clock_audit import fit_clock
from replay_nba_full_game_offline import actual_rows,Priors,rotations,EventRates
from simmah_nba_full_game_offline import simulate_game


def run(root,evidence,out,limit=None,shard=None,restarts=None):
 root=Path(root);out=Path(out);out.mkdir(exist_ok=True);games,allowed=load(root,evidence);clock_records=[observed(g) for g in games];hazard_records=[observe_hazards(g) for g in games]
 base=EventRates(**json.loads((root/'data/nba_models/event-rates-before-2026-04-09.json').read_text())['rates']);results=[];failures=[]
 checkpoint=out/'possession-replays.json'
 if checkpoint.exists():
  saved=json.loads(checkpoint.read_text());results=saved['results'];failures=saved['failures']
 completed={(r['game_id'],r['arm']) for r in results+failures}
 if len(completed)!=len(results)+len(failures):raise ValueError('Duplicate checkpoint rows')
 carried=len(results)
 if any(r['game_id'] not in allowed or r.get('fitted_hazards',{}).get('before',r.get('date'))!=r.get('date') for r in results):raise ValueError('Checkpoint target/date mismatch')
 arms=['restart_timing'] if restarts else ['clock_reference','shooting_fouls_and_rebounds']
 if restarts:
  from simmah_nba_restart_timing_offline import restart_observations,fit_restarts
  clean=set(json.loads((Path(out).parent/'nba-possession-results/reconciliation-summary.json').read_text())['clean_game_ids']);allowed=allowed&clean
  restart_records=[restart_observations(g) for g in games]
 if limit and int(limit)>0:
  traces=json.loads((Path(out).parent/'nba-possession-results/source-traces.json').read_text());clean={r['game_id'] for r in traces if not r['flags'] and not r['issues']}
  allowed={g['event_id'] for g in games if g['event_id'] in allowed and g['event_id'] in clean}
  allowed=set([g['event_id'] for g in games if g['event_id'] in allowed][:int(limit)])
 if shard:
  part,total=map(int,shard.split('/'));allowed={g['event_id'] for i,g in enumerate(games) if i%total==part and g['event_id'] in allowed}
 if any(r['game_id'] not in allowed or r['arm'] not in arms for r in results+failures):raise ValueError('Checkpoint scope does not match selected games/arms/shard')
 for gi,g in enumerate(games):
  if g['event_id'] not in allowed or all((g['event_id'],arm) in completed for arm in arms):continue
  players=actual_rows(g);teams=list(dict.fromkeys(r['team'] for r in players));by=[[r for r in players if r['team']==t and r['v'][0]>0] for t in teams]
  size=max(map(len,by));means=np.zeros((2,size));profiles=np.zeros((2,size,5));splits=np.tile([base.three_share,base.make_two,base.make_three,base.make_free_throw],(size*2,1));fouls=np.full(size*2,.09)
  prior=Priors(games,g['date'],base)
  for t,group in enumerate(by):
   raw=np.array([r['v'][0] for r in group]);means[t,:len(group)]=raw*240/raw.sum()
   sp,roles,fr=prior.for_names([r['name'] for r in group]);profiles[t,:len(group)]=roles;splits[t*size:t*size+len(group)]=sp;fouls[t*size:t*size+len(group)]=fr
  reg,ot=rotations(means,128,71+gi*17);clock=fit_clock(clock_records,g['date'],'empirical');hazards=fit_hazards(hazard_records,g['date'],base)
  if restarts:clock=fit_restarts(clock,restart_records,g['date'])
  for arm in arms:
   if (g['event_id'],arm) in completed:continue
   sf=arm in ['shooting_fouls','shooting_fouls_and_rebounds','restart_timing'];rb=arm in ['rebound_outcomes','shooting_fouls_and_rebounds','restart_timing']
   models=[replace(base,free_throw_trip=hazards['free_throw_trip_probability_per_action']) if sf else base]*2
   settings=None if arm=='clock_reference' else {**hazards,'and_one_probability_per_make':hazards['and_one_probability_per_make'] if sf else .03,
    'fg_rebound_outcomes':hazards['fg_rebound_outcomes'] if rb else [base.offensive_rebound,1-base.offensive_rebound,0.,0.],
    'ft_rebound_outcomes':hazards['ft_rebound_outcomes'] if rb else [base.offensive_rebound,1-base.offensive_rebound,0.,0.]}
   try:
    r=simulate_game(reg,profiles,models,33+gi,ot,shooting=splits,target_minutes=means,foul_rates=fouls,blowout=True,clock_model=clock,shot_hazards=settings,possession_audit=True)
    e=r['mechanics_counters'];attempts=r['attempts'];rebound_keys=[context+'_'+outcome for context in ['fg','ft'] for outcome in ['miss_rebound_opportunities','player_oreb','player_dreb','team_oreb','team_dreb']]
    trace=r['possession_trace'];stats=r['stats']
    duration=trace['completed_seconds_by_origin'].sum(axis=1)+trace['terminal_seconds_by_origin'].sum(axis=1)
    if not np.allclose(duration,r['elapsed_seconds'],atol=1e-7):raise RuntimeError('Possession clock partition failed')
    if not np.array_equal(trace['counts_by_team'].sum(axis=1),trace['completed_by_origin'].sum(axis=1)+trace['terminal_by_origin'].sum(axis=1)):raise RuntimeError('Possession count partition failed')
    row={'game_id':g['event_id'],'date':g['date'],'arm':arm,'restart_training':clock.get('restart_training'),'points':float(r['team_points'].sum(axis=1).mean()),
      'fga':float(attempts[:,:,0].sum(axis=1).mean()),'three_pa':float(attempts[:,:,1].sum(axis=1).mean()),'fta':float(attempts[:,:,2].sum(axis=1).mean()),
      'fgm':float(stats[:,:,0].sum(axis=1).mean()),'three_pm':float(stats[:,:,1].sum(axis=1).mean()),'ftm':float(stats[:,:,2].sum(axis=1).mean()),
      'turnovers':float((r['counters']['turnovers']+e['shot_clock_violations']).mean()),
      'player_oreb':float(e['offensive_rebounds'].mean()),'player_dreb':float(r['counters']['credited_rebounds'].mean()-e['offensive_rebounds'].mean()),
      'team_oreb':float(e['team_offensive_rebounds'].mean()),'team_dreb':float(e['team_defensive_rebounds'].mean()),
      'possessions':float(trace['counts_by_team'].sum(axis=1).mean()),'elapsed':float(r['elapsed_seconds'].mean()),
      'origins':trace['origins'],'completed_counts':trace['completed_by_origin'].mean(axis=0).tolist(),
      'completed_seconds':trace['completed_seconds_by_origin'].mean(axis=0).tolist(),
      'terminal_counts':trace['terminal_by_origin'].mean(axis=0).tolist(),'terminal_seconds':trace['terminal_seconds_by_origin'].mean(axis=0).tolist(),
      'oreb_tails':float(trace['oreb_continuation_tails'].mean()),'oreb_tail_seconds':float(trace['oreb_continuation_tail_seconds'].mean()),
      'max_clock_partition_error':float(abs(duration-r['elapsed_seconds']).max()),'scenario_zero':trace['scenario_zero']}
    results.append(row)

   except (ValueError,RuntimeError) as exc:failures.append({'game_id':g['event_id'],'arm':arm,'reason':str(exc)})
  partial=checkpoint.with_suffix('.partial.json');partial.write_text(json.dumps({'results':results,'failures':failures},indent=2));partial.replace(checkpoint)
  if gi%10==0 or g is games[-1]:print('possession replay',gi+1,'/',len(games),'failures',len(failures),flush=True)
 partial=checkpoint.with_suffix('.partial.json');partial.write_text(json.dumps({'results':results,'failures':failures},indent=2));partial.replace(checkpoint)
 print('completed',len(results),'failures',failures,flush=True)
if __name__=='__main__':run(*sys.argv[1:])
