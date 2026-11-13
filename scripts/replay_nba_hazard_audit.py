"""Fixed-clock conditional hazard ablation; no synthetic rebound delay."""
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


def run(root,evidence,out):
 root=Path(root);out=Path(out);out.mkdir(exist_ok=True);games,allowed=load(root,evidence);clock_records=[observed(g) for g in games];hazard_records=[observe_hazards(g) for g in games]
 base=EventRates(**json.loads((root/'data/nba_models/event-rates-before-2026-04-09.json').read_text())['rates']);results=[];failures=[]
 checkpoint=out/'hazard-replays.json'
 if checkpoint.exists():
  saved=json.loads(checkpoint.read_text());results=saved['results'];failures=saved['failures']
 completed={(r['game_id'],r['arm']) for r in results+failures}
 if len(completed)!=len(results)+len(failures):raise ValueError('Duplicate checkpoint rows')
 carried=len(results)
 if any(r['game_id'] not in allowed or r.get('fitted_hazards',{}).get('before',r.get('date'))!=r.get('date') for r in results):raise ValueError('Checkpoint target/date mismatch')
 arms=['clock_reference','shooting_fouls','rebound_outcomes','shooting_fouls_and_rebounds']
 for gi,g in enumerate(games):
  if g['event_id'] not in allowed or all((g['event_id'],arm) in completed for arm in arms):continue
  players=actual_rows(g);teams=list(dict.fromkeys(r['team'] for r in players));by=[[r for r in players if r['team']==t and r['v'][0]>0] for t in teams]
  size=max(map(len,by));means=np.zeros((2,size));profiles=np.zeros((2,size,5));splits=np.tile([base.three_share,base.make_two,base.make_three,base.make_free_throw],(size*2,1));fouls=np.full(size*2,.09)
  prior=Priors(games,g['date'],base)
  for t,group in enumerate(by):
   raw=np.array([r['v'][0] for r in group]);means[t,:len(group)]=raw*240/raw.sum()
   sp,roles,fr=prior.for_names([r['name'] for r in group]);profiles[t,:len(group)]=roles;splits[t*size:t*size+len(group)]=sp;fouls[t*size:t*size+len(group)]=fr
  reg,ot=rotations(means,128,71+gi*17);clock=fit_clock(clock_records,g['date'],'empirical');hazards=fit_hazards(hazard_records,g['date'],base)
  for arm in arms:
   if (g['event_id'],arm) in completed:continue
   sf=arm in ['shooting_fouls','shooting_fouls_and_rebounds'];rb=arm in ['rebound_outcomes','shooting_fouls_and_rebounds']
   models=[replace(base,free_throw_trip=hazards['free_throw_trip_probability_per_action']) if sf else base]*2
   settings=None if arm=='clock_reference' else {**hazards,'and_one_probability_per_make':hazards['and_one_probability_per_make'] if sf else .03,
    'fg_rebound_outcomes':hazards['fg_rebound_outcomes'] if rb else [base.offensive_rebound,1-base.offensive_rebound,0.,0.],
    'ft_rebound_outcomes':hazards['ft_rebound_outcomes'] if rb else [base.offensive_rebound,1-base.offensive_rebound,0.,0.]}
   try:
    r=simulate_game(reg,profiles,models,33+gi,ot,shooting=splits,target_minutes=means,foul_rates=fouls,blowout=True,clock_model=clock,shot_hazards=settings)
    e=r['mechanics_counters'];attempts=r['attempts'];rebound_keys=[context+'_'+outcome for context in ['fg','ft'] for outcome in ['miss_rebound_opportunities','player_oreb','player_dreb','team_oreb','team_dreb']]
    results.append({'game_id':g['event_id'],'date':g['date'],'arm':arm,'points':float(r['team_points'].sum(axis=1).mean()),'fga':float(attempts[:,:,0].sum(axis=1).mean()),'fta':float(attempts[:,:,2].sum(axis=1).mean()),
     'shooting_fouls':float(e['shooting_fouls'].mean()),'non_andone_shooting_fouls':float(e['non_andone_shooting_fouls'].mean()),'and_one_fouls':float(e['and_one_fouls'].mean()),
     'player_oreb':float(e['offensive_rebounds'].mean()),'player_dreb':float(r['counters']['credited_rebounds'].mean()-e['offensive_rebounds'].mean()),
     'team_oreb':float(e['team_offensive_rebounds'].mean()),'team_dreb':float(e['team_defensive_rebounds'].mean()),'shot_clock_violations':float(e['shot_clock_violations'].mean()),
     'mean_regulation_seconds':float(r['clock_audit']['regulation_seconds'].sum(axis=1).mean()),'max_regulation_error':float(abs(r['clock_audit']['regulation_seconds'].sum(axis=1)-2880).max()),
     'unresolved_overtime':int(r['requires_overtime'].sum()),'fitted_hazards':hazards,'rebound_context_counts':{k:float(e[k].mean()) for k in rebound_keys}})
   except (ValueError,RuntimeError) as exc:failures.append({'game_id':g['event_id'],'arm':arm,'reason':str(exc)})
  partial=checkpoint.with_suffix('.partial.json');partial.write_text(json.dumps({'results':results,'failures':failures},indent=2));partial.replace(checkpoint)
  if gi%10==0 or g is games[-1]:print('hazard replay',gi+1,'/',len(games),'failures',len(failures),flush=True)
 partial=checkpoint.with_suffix('.partial.json');partial.write_text(json.dumps({'results':results,'failures':failures},indent=2));partial.replace(checkpoint)
 summary={'checkpoint_records_carried':carried,'fixed_games':len(allowed),'draws_per_arm_game':128,'original_roster_failure_excluded_unresolved':'401909909','live_enabled':False,'arms':{},'failures':failures}
 for arm in arms:
  rows=[r for r in results if r['arm']==arm];summary['arms'][arm]={'completed':len(rows),**{k:float(np.mean([r[k] for r in rows])) for k in ['points','fga','fta','shooting_fouls','non_andone_shooting_fouls','and_one_fouls','player_oreb','player_dreb','team_oreb','team_dreb','shot_clock_violations']},'max_regulation_error':max(r['max_regulation_error'] for r in rows),
  'rebound_context_counts':{k:float(np.mean([r['rebound_context_counts'][k] for r in rows])) for k in results[0]['rebound_context_counts']}}
 (out/'hazard-summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
if __name__=='__main__':run(*sys.argv[1:])
