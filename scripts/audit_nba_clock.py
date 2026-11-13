"""Offline event/clock audit. No production writes or roster repair."""
import json,gzip,zipfile,sys,hashlib
from pathlib import Path
from collections import Counter,defaultdict
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from replay_nba_full_game_offline import actual_rows,Priors,rotations,EventRates
BUCKETS=['other','after_oreb','after_foul','after_ft','after_make','after_dreb','after_turnover']
def sec(e):
 raw=e['clock']['displayValue'];a=str(raw).split(':');return float(a[0])*60+float(a[1]) if len(a)>1 else float(raw)
def kind(e):
 k=e.get('type',{}).get('text','').lower();text=e.get('text','').lower()
 if 'turnover' in k:return 'violation' if 'shot clock' in k+' '+text else 'turnover'
 if 'foul' in k:
  if 'turnover' in k:return 'turnover'
  if 'shooting' in k:return 'shooting_foul'
  if 'technical' in k:return 'technical'
  return 'nonshooting_foul'
 if e.get('pointsAttempted')==1 or 'free throw' in k:return 'ft'
 if e.get('shootingPlay') and e.get('pointsAttempted') in (2,3):return 'make' if e.get('scoringPlay') else 'miss'
 if k=='offensive rebound':return 'oreb' if e.get('participants') else 'team_oreb'
 if k=='defensive rebound':return 'dreb' if e.get('participants') else 'team_dreb'
 return 'admin'
def observed(g):
 counts=Counter();ledger=Counter();regledger=Counter();ft_deadball=0.;profiles=defaultdict(list);phase='other';prev=None;last_live=None;last_kind=None;issues=[];periods=set()
 for e in g['events']:
  period=int(e['period']['number']);remaining=sec(e);periods.add(period)
  if prev is None or prev[0]!=period:
   phase='other';last_live=None;last_kind=None;cursor=720 if period<=4 else 300
  else:cursor=prev[1]
  delta=cursor-remaining
  if delta<0:issues.append({'event':e['id'],'reason':'clock_increase','seconds':delta})
  else:
   ledger[phase]+=delta
   if period<=4:regledger[phase]+=delta
  k=kind(e)
  if delta>=0 and k=='ft' and phase in ['after_foul','after_ft']:ft_deadball+=delta
  if k not in ['admin']:counts[k]+=1
  if k in ['oreb','dreb'] and last_kind=='miss' and last_live is not None:
   lp,lc,_=last_live;gap=lc-remaining
   if lp==period and 0<=gap<=30:profiles['miss_to_rebound'].append(gap)
  if k in ['make','miss','turnover','violation','shooting_foul','nonshooting_foul'] and last_live is not None:
   last_period,last_clock,last_phase=last_live;gap=last_clock-remaining
   if period==last_period and 0<gap<=40 and k!='violation':profiles[last_phase].append(gap)
  if k=='oreb':phase='after_oreb'
  elif k=='dreb':phase='after_dreb'
  elif k=='make':phase='after_make'
  elif k in ['shooting_foul','nonshooting_foul']:phase='after_foul'
  elif k=='ft':phase='after_ft'
  elif k in ['turnover','violation']:phase='after_turnover'
  elif k=='miss':phase='other'
  if k!='admin':last_live=(period,remaining,phase);last_kind=k
  prev=(period,remaining)
 expected=2880+300*max(0,max(periods)-4)
 return {'game_id':g['event_id'],'date':g['date'],'counts':dict(counts),'clock_seconds':dict(ledger),'regulation_clock_seconds':dict(regledger),'ft_deadball_elapsed_seconds':ft_deadball,'observed_seconds':sum(ledger.values()),'expected_seconds':expected,'clock_issues':issues,'profiles':dict(profiles)}
def load(root,evidence):
 with zipfile.ZipFile(next(Path(evidence).glob('*Comprehensive_Audit*.zip'))) as z:inventory=json.loads(z.read('pbp-audit.json'))['inventory']
 with zipfile.ZipFile(next(Path(evidence).glob('*Full_Game_Offline_Replay*.zip'))) as z:old=json.loads(z.read('conditional-distributions.json'))
 allowed={r['game_id'] for r in old if r['status']=='simulated'};hashes={r['game_id']:r['sha256'] for r in inventory};games=[]
 for p in sorted((Path(root)/'data/nba_pbp').glob('*/*.json.gz')):
  g=json.loads(gzip.decompress(p.read_bytes()))
  if g['event_id'] not in hashes:continue
  if hashlib.sha256(p.read_bytes()).hexdigest()!=hashes[g['event_id']]:raise ValueError('Frozen source hash mismatch')
  games.append(g)
 games.sort(key=lambda g:(g['date'],g['event_id']))
 return games,allowed
if __name__=='__main__':
 root,evidence,out=sys.argv[1:];games,allowed=load(root,evidence);rows=[observed(g) for g in games if g['event_id'] in allowed];Path(out).mkdir(exist_ok=True)
 summary={'games':len(rows),'events':sum(len(g['events']) for g in games if g['event_id'] in allowed),'mean_counts':{k:float(np.mean([r['counts'].get(k,0) for r in rows])) for k in sorted(set(k for r in rows for k in r['counts']))},'mean_clock_seconds':{k:float(np.mean([r['clock_seconds'].get(k,0) for r in rows])) for k in BUCKETS},'mean_regulation_clock_seconds':{k:float(np.mean([r['regulation_clock_seconds'].get(k,0) for r in rows])) for k in BUCKETS},'mean_ft_deadball_elapsed_seconds':float(np.mean([r['ft_deadball_elapsed_seconds'] for r in rows])),'mean_observed_seconds':float(np.mean([r['observed_seconds'] for r in rows])),'mean_expected_seconds':float(np.mean([r['expected_seconds'] for r in rows])), 'interval_profiles':{k:{'n':len(v),'mean':float(np.mean(v)),'p90':float(np.quantile(v,.9))} for k in BUCKETS if (v:=[v for r in rows for v in r['profiles'].get(k,[])])}}
 (Path(out)/'observed-clock.json').write_text(json.dumps({'summary':summary,'games':rows},indent=2));print(json.dumps(summary,indent=2))
