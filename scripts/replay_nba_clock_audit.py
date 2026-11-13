"""Fixed-set, fixed-minutes/roles clock-only conditional ablation."""
import json,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from audit_nba_clock import load,observed,BUCKETS
from replay_nba_full_game_offline import actual_rows,Priors,rotations,EventRates
from simmah_nba_full_game_offline import simulate_game
from simmah_nba_scoring import score_nba

def fit_clock(records,before,mode):
 prior=[r for r in records if r['date']<before];profiles={k:sorted(v for r in prior for v in r['profiles'].get(k,[])) for k in BUCKETS+['miss_to_rebound']}
 den=sum(sum(r['counts'].get(k,0) for k in ['make','miss','turnover','violation','shooting_foul','nonshooting_foul','technical']) for r in prior)
 violation=sum(r['counts'].get('violation',0) for r in prior)/den if den else 0.
 return {'mode':mode,'profiles':profiles,'violation_probability':violation,'training_games':len(prior),'before':before}

def run(root,evidence,out):
 root=Path(root);out=Path(out);out.mkdir(exist_ok=True);games,allowed=load(root,evidence);records=[observed(g) for g in games]
 base=EventRates(**json.loads((root/'data/nba_models/event-rates-before-2026-04-09.json').read_text())['rates'])
 rows=[];failures=[]
 arms=['legacy','legal_clock','empirical_clock']
 for gi,g in enumerate(games):
  if g['event_id'] not in allowed:continue
  players=actual_rows(g);teams=list(dict.fromkeys(r['team'] for r in players));by=[[r for r in players if r['team']==t and r['v'][0]>0] for t in teams]
  size=max(map(len,by));means=np.zeros((2,size));profiles=np.zeros((2,size,5));splits=np.tile([base.three_share,base.make_two,base.make_three,base.make_free_throw],(size*2,1));fouls=np.full(size*2,.09)
  prior=Priors(games,g['date'],base)
  for t,group in enumerate(by):
   raw=np.array([r['v'][0] for r in group]);means[t,:len(group)]=raw*240/raw.sum()
   sp,roles,fr=prior.for_names([r['name'] for r in group]);profiles[t,:len(group)]=roles;splits[t*size:t*size+len(group)]=sp;fouls[t*size:t*size+len(group)]=fr
  reg,ot=rotations(means,128,71+gi*17)
  for arm in arms:
   model=None if arm=='legacy' else fit_clock(records,g['date'],'empirical' if arm.startswith('empirical') else 'truncated')
   try:
    r=simulate_game(reg,profiles,[base]*2,33+gi,ot,shooting=splits,target_minutes=means,foul_rates=fouls,blowout=True,clock_model=model)
    extra=r['mechanics_counters'];audit=r['clock_audit'];fga=r['attempts'][:,:,0].sum(axis=1);fta=r['attempts'][:,:,2].sum(axis=1)
    rec={'game_id':g['event_id'],'date':g['date'],'arm':arm,'status':'simulated','training_games':None if model is None else model['training_games'],
      'points':float(r['team_points'].sum(axis=1).mean()),'fga':float(fga.mean()),'fta':float(fta.mean()),'player_turnovers':float(r['counters']['turnovers'].mean()),
      'shot_clock_violations':float(extra['shot_clock_violations'].mean()),'turnovers_including_clock':float((r['counters']['turnovers']+extra['shot_clock_violations']).mean()),
      'shooting_fouls':float(extra['shooting_fouls'].mean()),'nonshooting_fouls':float(extra['nonshooting_fouls'].mean()),'oreb':float(extra['offensive_rebounds'].mean()),
      'changes_of_control':float(extra['possession_changes'].mean()),'possessions_proxy_per_team':float(((fga+.44*fta-extra['offensive_rebounds']+r['counters']['turnovers']+extra['shot_clock_violations'])/2).mean()),
      'clock_seconds':dict(zip(BUCKETS,audit['seconds'].mean(axis=0).tolist())),
      'regulation_clock_seconds':dict(zip(BUCKETS,audit['regulation_seconds'].mean(axis=0).tolist())),
      'clock_actions':dict(zip(BUCKETS,audit['actions'].mean(axis=0).tolist())),
      'expirations_by_origin':dict(zip(BUCKETS,audit['expirations'].mean(axis=0).tolist())),
      'fta_administration_seconds':audit['free_throw_administration_seconds'],'extra_transition_delay_seconds':audit['separate_transition_delay_seconds'],
      'overtime_fraction':float((r['overtime_periods']>0).mean()),'unresolved_overtime_trials':int(r['requires_overtime'].sum())}
    high=[]
    for t,group in enumerate(by):
     for k,p in enumerate(group):
      if p['v'][0]<30:continue
      actual=float(score_nba('FanDuel',**p['actual']));p90,p95=np.quantile(r['scores'][:,t*size+k],[.9,.95]);high.append([actual>p90,actual>p95])
    rec['high_minute_rows']=len(high);rec['above_p90_count']=sum(v[0] for v in high);rec['above_p95_count']=sum(v[1] for v in high)
    rows.append(rec)
   except (ValueError,RuntimeError) as exc:failures.append({'game_id':g['event_id'],'arm':arm,'reason':str(exc)})
  if gi%20==0 or g is games[-1]:
   (out/'clock-replays.json').write_text(json.dumps({'rows':rows,'failures':failures},indent=2,default=lambda v:bool(v) if isinstance(v,np.bool_) else int(v)));print('clock replay',gi+1,'/',len(games),'failures',len(failures),flush=True)
 (out/'clock-replays.json').write_text(json.dumps({'rows':rows,'failures':failures},indent=2,default=lambda v:bool(v) if isinstance(v,np.bool_) else int(v)))
 summary={'fixed_target_games':len(allowed),'reference_roster_failure_preserved':'401909909','draws_per_game_arm':128,'arms':{},'live_enabled':False}
 for arm in arms:
  rr=[r for r in rows if r['arm']==arm];summary['arms'][arm]={'completed':len(rr),**{k:float(np.mean([r[k] for r in rr])) for k in ['points','fga','fta','player_turnovers','shot_clock_violations','turnovers_including_clock','shooting_fouls','nonshooting_fouls','oreb','changes_of_control','possessions_proxy_per_team']},
    'clock_seconds':{k:float(np.mean([r['clock_seconds'][k] for r in rr])) for k in BUCKETS},'regulation_clock_seconds':{k:float(np.mean([r['regulation_clock_seconds'][k] for r in rr])) for k in BUCKETS},
    'clock_actions':{k:float(np.mean([r['clock_actions'][k] for r in rr])) for k in BUCKETS},'expirations_by_origin':{k:float(np.mean([r['expirations_by_origin'][k] for r in rr])) for k in BUCKETS},
    'above_p90':float(sum(r['above_p90_count'] for r in rr)/sum(r['high_minute_rows'] for r in rr)), 'above_p95':float(sum(r['above_p95_count'] for r in rr)/sum(r['high_minute_rows'] for r in rr))}
 (out/'clock-replay-summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
if __name__=='__main__':run(*sys.argv[1:])
