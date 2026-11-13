"""Earlier-date restart-to-first-action timing, never full-possession padding."""
from simmah_nba_possession_trace_offline import reconstruct_trace,kind
from scripts.audit_nba_clock import sec
KEYS=('period_start','dead_ball_inbound','after_make')
def restart_observations(game):
 trace=reconstruct_trace(game);events={str(e['id']):e for e in game['events']};profiles={k:[] for k in KEYS}
 for p in trace['possessions']:
  if not p['usable'] or p['origin'] not in KEYS:continue
  # Terminal possessions are right-censored, not observed action durations.
  for eid in p['event_ids']:
   e=events[eid]
   if kind(e) not in ['make','miss','turnover','violation','shooting_foul','nonshooting_foul']:continue
   dt=p['start_clock']-sec(e)
   if 0<dt<24:profiles[p['origin']].append(float(dt))
   break
 return {'game_id':game['event_id'],'date':game['date'],'profiles':profiles}
def fit_restarts(clock,records,before):
 prior=[r for r in records if r['date']<before]
 out={**clock,'profiles':{k:list(v) for k,v in clock['profiles'].items()},'restart_profiles':True}
 counts={}
 for key in KEYS:
  values=sorted(v for r in prior for v in r['profiles'].get(key,[]));counts[key]=len(values)
  # With no prior evidence use the existing post-make support, not target-day data.
  out['profiles'][key]=values or list(clock['profiles'].get('after_make',[]))
 out['restart_training']={'before':before,'games':len(prior),'counts':counts,'fallback':'earlier-date after_make, then incumbent gamma'}
 return out
