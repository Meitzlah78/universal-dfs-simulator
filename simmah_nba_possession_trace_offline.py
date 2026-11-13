"""Auditable ESPN possession boundaries and continuation tails, offline only.

Counts positive-clock period-ending control as a terminal possession. Ordinary
OREB continues possession; made basket with an and-one closes after its trip.
Ambiguous control changes remain flagged, never called clean exact counts.
"""
import re
from collections import Counter
from scripts.audit_nba_clock import kind as clock_kind,sec

def kind(event):
    k=clock_kind(event)
    if k=='admin' and 'turnover' in event.get('text','').lower():return 'turnover'
    return k

def reconstruct_trace(game):
 teams=[str(t['team']['id']) for t in game['boxscore']['players']]
 if len(teams)!=2 or len(set(teams))!=2:raise ValueError('Two source teams required')
 players={str(a['athlete']['id']):str(t['team']['id']) for t in game['boxscore']['players'] for s in t['statistics'] for a in s['athletes']}
 events=game['events'];rows=[];current=None;pending=None;period=None;last_clock=None;pending_basket=False;pending_miss=False;ft_dead=False;retained=False;outside_points=0;issues=[];ignored_team_rebounds=0
 def other(t):return teams[1] if t==teams[0] else teams[0]
 def team(e):
  t=str(e.get('team',{}).get('id',''))
  if t in teams:return t
  actor=(e.get('participants') or [{}])[0].get('athlete',{}).get('id')
  return players.get(str(actor))
 def start(t,clock,origin,flags=None):
  return {'offense':t,'period':period,'start_clock':clock,'origin':origin,'points':0,'oreb_clocks':[],'flags':list(flags or []),'event_ids':[]}
 def ensure(t,clock):
  nonlocal current,pending
  if t not in teams:return False
  if current is None:
   if pending is None:current=start(t,720 if period<=4 else 300,'period_start')
   else:
    expected,when,origin=pending;current=start(t,when,origin,[] if expected in (None,t) else ['unexplained_control_change']);pending=None
  elif current['offense']!=t:
   current['flags'].append('unexplained_control_change');close(clock,'unexplained_change',False)
   current=start(t,clock,'unknown_boundary',['left_censored'])
  return True
 def close(clock,reason,completed=True):
  nonlocal current,pending
  if current is None:return
  duration=current['start_clock']-clock
  if duration<-.000001:current['flags'].append('clock_increase')
  current.update(end_clock=clock,seconds=max(0,duration),end_reason=reason,completed=completed)
  current['flags']=sorted(set(current['flags']));current['usable']=not current['flags']
  current['oreb_tail_seconds']=[max(0,t-clock) for t in current['oreb_clocks']]
  if duration>0 or current['event_ids']:rows.append(current)
  current=None
 def next_pos(t,clock,origin):
  nonlocal pending
  pending=(t,clock,origin)
 def points(e):
  if not e.get('scoringPlay'):return 0
  return int(e.get('scoreValue') or e.get('pointsAttempted') or 0)
 def has_and_one(index,e):
  p=e['period']['number'];clock=sec(e);who=(e.get('participants') or [{}])[0].get('athlete',{}).get('id')
  if who is None:return False
  seen_foul=False
  for n in events[index+1:]:
   if n['period']['number']!=p or not 0<=clock-sec(n)<=2:break
   nk=kind(n)
   if nk=='shooting_foul':seen_foul=True
   if nk in ['make','miss','turnover','violation']:break
   text=n.get('text','').lower();parts=n.get('participants') or []
   if seen_foul and kind(n)=='ft' and re.search(r'1\s+of\s+1',text) and 'technical' not in text and parts and str(parts[0].get('athlete',{}).get('id'))==str(who):return True
  return False
 for i,e in enumerate(events):
  p=int(e['period']['number']);clock=sec(e);k=kind(e);raw=e.get('type',{}).get('text','').lower();t=team(e);text=e.get('text','').lower()
  if p!=period:
   if current is not None:current['flags'].append('missing_period_end');close(0,'period_change',False)
   period=p;current=None;pending=None;pending_basket=False;pending_miss=False;ft_dead=False;retained=False
  if last_clock is not None and p==last_clock[0] and clock>last_clock[1]:issues.append({'event':e['id'],'reason':'clock_increase'})
  last_clock=(p,clock)
  if raw in ['end period','end game']:
   if current is None and pending is not None and pending[1]>0:current=start(pending[0],pending[1],pending[2]);pending=None
   close(clock,'period_end',False);pending=None;continue
  if 'jump' in raw and ('ball' in raw):
   winner=t
   if winner is not None:
    if current is not None and winner!=current['offense']:close(clock,'jump_ball_control');next_pos(winner,clock,'dead_ball_inbound')
    elif current is None:next_pos(winner,clock,'period_start' if clock==(720 if p<=4 else 300) else 'dead_ball_inbound')
   elif current is not None:current['flags'].append('unresolved_jump_ball')
   continue
  if k=='ft':
   trip=re.search(r'(\d)\s+of\s+(\d)',text+' '+raw)
   special=retained or 'technical' in text+' '+raw or 'flagrant' in text+' '+raw
   if special:
    outside_points+=points(e);ft_dead=True
    if trip is None or trip[1]==trip[2]:retained=False
    continue
   if not ensure(t,clock):issues.append({'event':e['id'],'reason':'unknown_ft_team'});continue
   current['event_ids'].append(str(e['id']));current['points']+=points(e)
   if trip is None:current['flags'].append('unknown_ft_trip');ft_dead=True;continue
   final=trip[1]==trip[2];ft_dead=not final
   pending_miss=bool(final and not e.get('scoringPlay'))
   if final and e.get('scoringPlay'):
    close(clock,'final_ft');next_pos(other(t),clock,'after_ft');pending_basket=False
   continue
  if k in ['oreb','dreb','team_oreb','team_dreb']:
   if ft_dead:continue
   if k in ['team_oreb','team_dreb']:
    if not pending_miss:ignored_team_rebounds+=1;continue
    # Prefer explicit player control evidence over a same-clock administrative
    # team-rebound marker. A new shot/trip/turnover ends this lookup window.
    future_player=False
    for nxt in events[i+1:]:
     if nxt['period']['number']!=p or sec(nxt)!=clock:break
     nk=kind(nxt)
     if nk in ['make','miss','ft','turnover','violation']:break
     if nk in ['oreb','dreb']:future_player=True;break
    if future_player:ignored_team_rebounds+=1;continue
   pending_miss=False
   if t is None:issues.append({'event':e['id'],'reason':'unknown_rebound_team'});continue
   if k in ['oreb','team_oreb']:
    if pending_basket:
     if current is not None:close(clock,'and_one_basket');next_pos(t,clock,'after_andone_oreb')
     pending_basket=False
    else:
     ensure(t,clock)
     if k=='oreb':current['oreb_clocks'].append(clock)
     current['event_ids'].append(str(e['id']))
   else:
    ensure(other(t),clock)
    current['event_ids'].append(str(e['id']));close(clock,'defensive_rebound');next_pos(t,clock,'after_dreb' if k=='dreb' else 'dead_ball_inbound');pending_basket=False
   continue
  if k in ['make','miss','turnover','violation']:
   if not ensure(t,clock):issues.append({'event':e['id'],'reason':'unknown_action_team'});continue
   current['event_ids'].append(str(e['id']));current['points']+=points(e);ft_dead=False;pending_miss=k=='miss'
   if k in ['turnover','violation']:close(clock,'turnover');next_pos(other(t),clock,'after_turnover');pending_basket=False
   elif k=='make':
    pending_basket=has_and_one(i,e)
    if not pending_basket:close(clock,'made_fg');next_pos(other(t),clock,'after_make')
   continue
  if 'flagrant' in raw or 'clear path' in raw or 'transition take' in raw or 'away from play' in raw:retained=True
  if k in ['shooting_foul','nonshooting_foul'] and current is None and t in teams and 'offensive' not in raw:
   if pending is not None:ensure(pending[0],clock)
   elif k=='shooting_foul':ensure(other(t),clock)
  if current is not None:current['event_ids'].append(str(e['id']))
 if current is not None:current['flags'].append('unterminated');close(last_clock[1],'end_of_data',False)
 return {'game_id':game['event_id'],'ignored_administrative_team_rebounds':ignored_team_rebounds,'possessions':rows,'issues':issues,'outside_possession_points':outside_points,
         'flags':dict(Counter(flag for r in rows for flag in r['flags'])),
         'reconciled_points':sum(r['points'] for r in rows)+outside_points,
         'official_points':game['home_score']+game['away_score']}
