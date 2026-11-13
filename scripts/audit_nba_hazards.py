"""Earlier-date shot/foul and live-miss rebound exposure audit."""
from collections import Counter
import re,json,sys,math
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from audit_nba_clock import kind,sec,load

def actor(event):
 p=event.get('participants') or []
 return str(p[0].get('athlete',{}).get('id','')) if p else ''

def observe_hazards(game):
 c=Counter();last_make=None;pending_sf=None;pending_miss=None;previous_period=None
 for event in game['events']:
  period=int(event['period']['number']);time=sec(event);k=kind(event)
  if period!=previous_period:last_make=pending_sf=pending_miss=None
  previous_period=period
  if k in ['make','miss']:
   c['fga']+=1;last_make=(period,time,actor(event)) if k=='make' else None;pending_sf=None
   if k=='make':c['fgm']+=1;pending_miss=None
   else:c['fg_miss']+=1;pending_miss='fg'
  elif k=='shooting_foul':
   c['shooting_fouls']+=1;pending_sf=event['id'];pending_miss=None
  elif k=='ft':
   text=event.get('text','').lower();m=re.search(r'(\d)\s+of\s+(\d)',text)
   technical='technical' in text or 'technical' in event.get('type',{}).get('text','').lower()
   if m and m.group(1)=='1':
    c['numbered_'+m.group(2)+'_shot_trips']+=1
    if m.group(2)=='1' and not technical and actor(event) and last_make==(period,time,actor(event)) and pending_sf is not None:
     c['verified_and_one_fouls']+=1;pending_sf=None
   final=bool(m and m.group(1)==m.group(2))
   if final and not technical and not event.get('scoringPlay'):
    c['final_ft_misses']+=1;pending_miss='ft'
   else:pending_miss=None
  elif k in ['oreb','dreb','team_oreb','team_dreb']:
   if pending_miss is not None:
    c[pending_miss+'_'+k]+=1;pending_miss=None
  elif k in ['turnover','violation','nonshooting_foul','technical']:
   pending_miss=None
 return {'game_id':game['event_id'],'date':game['date'],'counts':dict(c)}

def fit_hazards(records,before,base,prior_exposures=100):
 base.validate()
 date.fromisoformat(str(before))
 if not math.isfinite(prior_exposures) or prior_exposures<=0:raise ValueError('Positive finite prior exposure required')
 if 1-base.turnover-.055-.002<=0:raise ValueError('No supported shot-opportunity mass')
 counts=Counter()
 eligible=[r for r in records if r['date']<before]
 for r in eligible:counts.update(r['counts'])
 one=counts['verified_and_one_fouls'];sf=counts['shooting_fouls'];normal=sf-one
 if normal<0:raise ValueError('Verified and-one subset exceeds shooting-foul count')
 opportunity_mass=1-base.turnover-.055-.002
 incumbent=base.free_throw_trip/opportunity_mass
 h=(normal+prior_exposures*incumbent)/(counts['fga']+normal+prior_exposures)
 andone=(one+prior_exposures*.03)/(counts['fgm']+prior_exposures)
 def rebound(prefix):
  keys=['oreb','dreb','team_oreb','team_dreb']
  exposures=[counts[prefix+'_'+k] for k in keys]
  prior=[base.offensive_rebound,1-base.offensive_rebound,0.,0.]
  denominator=sum(exposures)+prior_exposures
  return [(n+prior_exposures*p)/denominator for n,p in zip(exposures,prior)]
 return {'before':before,'training_games':len(eligible),'prior_exposures':prior_exposures,'normal_shooting_foul_probability_per_opportunity':h,
         'free_throw_trip_probability_per_action':opportunity_mass*h,'and_one_probability_per_make':andone,
         'fg_rebound_outcomes':rebound('fg'),'ft_rebound_outcomes':rebound('ft'),'counts':dict(counts),'live_enabled':False}

if __name__=='__main__':
 games,allowed=load(sys.argv[1],sys.argv[2]);rows=[observe_hazards(g) for g in games];c=Counter()
 for r in rows:
  if r['game_id'] in allowed:c.update(r['counts'])
 out={'target_games':len(allowed),'counts':dict(c),'per_game':{k:v/len(allowed) for k,v in c.items()},'games':rows}
 Path(sys.argv[3]).write_text(json.dumps(out,indent=2));print(json.dumps({k:v for k,v in out.items() if k!='games'},indent=2))
