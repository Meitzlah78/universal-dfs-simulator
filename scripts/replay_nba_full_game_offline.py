"""Integrated offline mechanics replay, separating conditional checks from forecasts.

No production writes. Uses frozen pregame builds; the companion conditional
script separately evaluates all 227 source games.
"""
import argparse,json,gzip,io,zipfile,sys,hashlib
from pathlib import Path
from collections import defaultdict
from functools import partial
from unittest.mock import patch
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_nba_engine import EventRates,simulate_game as baseline_game
from simmah_nba_full_game_offline import simulate_game as challenger_game
from simmah_nba_pregame import PregameEngine
from simmah_nba_rotation_schedule import build_rotation
from simmah_nba_minutes import draw_regulation_minutes
from simmah_nba_learning import name_key
from simmah_nba_projections import team_key
from simmah_nba_scoring import score_nba


def minutes(v):
 a=str(v).split(':');return float(a[0])+(float(a[1])/60 if len(a)>1 else 0)

def actual_rows(game):
 result=[]
 for team in game['boxscore']['players']:
  for section in team['statistics']:
   for row in section['athletes']:
    who=row['athlete'];s=dict(zip(section['names'],row.get('stats',[])));dnp=bool(row.get('didNotPlay'))
    values=np.zeros(11)
    if not dnp:
     if not s or s.get('MIN') in ('','--',None):continue
     fg,fa=map(int,s['FG'].split('-'));tm,ta=map(int,s['3PT'].split('-'));fm,fta=map(int,s['FT'].split('-'))
     values=np.array([minutes(s['MIN']),fg,fa,tm,ta,fm,fta,*[float(s[k]) for k in ['AST','REB','STL','BLK']]])
    result.append({'id':str(who['id']),'name':name_key(who.get('displayName',who.get('fullName',''))),'team':canon(team['team']['abbreviation']),
                   'v':values,'pf':0 if dnp else float(s['PF']),'to':0 if dnp else float(s['TO']),'dnp':dnp,
                   'actual':dict(points=0 if dnp else float(s['PTS']),threes=values[3],rebounds=values[8],assists=values[7],steals=values[9],blocks=values[10],turnovers=0 if dnp else float(s['TO']))})
 return result

def canon(t):return {'WSH':'WAS','UTAH':'UTA'}.get(team_key(t),team_key(t))

class Priors:
 def __init__(self,games,before,base):
  self.base=base;self.data=defaultdict(lambda:np.zeros(12));self.games=0
  for game in games:
   if game['date']>=before:continue
   self.games+=1
   for row in actual_rows(game):self.data[row['name']]+=np.r_[row['v'],row['pf']]
 def for_names(self,names):
  shooting=[];roles=[];fouls=[]
  # Shrink player components toward fixed pre-archive league model. These are
  # deliberately simple priors, not fitted on the replay target's box score.
  for name in names:
   v=self.data[name];m,fg,fa,tm,ta,fm,fta,ast,reb,stl,blk,pf=v
   b=self.base
   shooting.append([(ta+100*b.three_share)/(fa+100),(fg-tm+100*b.make_two)/(fa-ta+100),(tm+100*b.make_three)/(ta+100),(fm+100*b.make_free_throw)/(fta+100)])
   roles.append([(fa+120*.4)/(m+120),(ast+120*.1)/(m+120),(reb+120*.15)/(m+120),(stl+120*.03)/(m+120),(blk+120*.02)/(m+120)])
   fouls.append((pf+120*.09)/(m+120))
  return np.asarray(shooting),np.asarray(roles),np.asarray(fouls)

def rotations(means,n,seed):
 size=means.shape[1];reg=[];ot=[]
 for t in (0,1):
  sampled=draw_regulation_minutes(means[t],n,seed+t)
  reg.append(build_rotation(sampled,seed+10+t,t*size))
  ot.append(np.stack([build_rotation(np.tile(means[t]*5/48,(n,1)),seed+100+k*7+t,t*size,period_minutes=5) for k in range(10)],axis=1))
 return np.stack(reg,axis=1),np.stack(ot,axis=1)

def run(root,evidence,output,draws=512):
 root=Path(root);out=Path(output);out.mkdir(exist_ok=True)
 audit_path=next(Path(evidence).glob('Simmah_NBA_Comprehensive_Audit*.zip'))
 with zipfile.ZipFile(audit_path) as z:
  audit=json.loads(z.read('pbp-audit.json'));forecasts=pd.read_csv(io.BytesIO(z.read('player-forecast-audit.csv')),dtype={'player_id':str})
 ids={v['game_id'] for v in audit['inventory']};expected_hash={v['game_id']:v['sha256'] for v in audit['inventory']}
 games=[]
 for path in sorted((root/'data/nba_pbp').glob('*/*.json.gz')):
  g=json.loads(gzip.decompress(path.read_bytes()))
  if g['event_id'] not in ids:continue
  if hashlib.sha256(path.read_bytes()).hexdigest()!=expected_hash[g['event_id']]:raise ValueError('Frozen PBP source changed')
  games.append(g)
 if len(games)!=227:raise ValueError('Incomplete frozen PBP corpus')
 games.sort(key=lambda g:(g['date'],g['event_id']))
 base=EventRates(**json.loads((root/'data/nba_models/event-rates-before-2026-04-09.json').read_text())['rates'])
 # First grade strict frozen pregame observations. No current-game actuals feed
 # priors, roster selection, targets, calibration or sampling.
 graded=[];forecast_diagnostics=[]
 for archive in sorted(Path(evidence).glob('*Calibration_Solver*.zip')):
  with zipfile.ZipFile(archive) as z:data=z.read('original_build.zip') if 'original_build.zip' in z.namelist() else archive.read_bytes()
  with zipfile.ZipFile(io.BytesIO(data)) as z:
   for name,info in json.loads(z.read('manifest.json'))['files'].items():
    if hashlib.sha256(z.read(name)).hexdigest()!=info['sha256']:raise ValueError('Frozen build source changed')
   meta=json.loads(z.read('inputs/player_pool.json'));manifest=json.loads(z.read('manifest.json'));markets=json.loads(z.read('inputs/markets.json'))
  pool=pd.DataFrame(meta['rows']);pool.attrs=meta['attrs'];pool['Player ID']=pool['Player ID'].astype(str)
  pool['Team']=pool.Team.map(canon);pool['Opponent']=pool.Opponent.map(canon)
  package=next(p for p in forecasts.package.astype(str).unique() if p in archive.name)
  prior=Priors(games,manifest['slate_date'],base)
  # Markets may be serialized as a bare list or an object. Fail on unknown shape.
  if isinstance(markets,dict):markets=markets.get('markets',markets.get('rows',[]))
  for market in markets:market['teams']=[canon(v) for v in market['teams']]
  full=PregameEngine(pool,markets,base,platform='DraftKings' if 'DraftKings' in archive.name else 'FanDuel',parallel=False)
  forecast_diag={'package':package,'games':[],'prior_games':prior.games,'draws':draws}
  for gi,(market,groups) in enumerate(full.games):
   active_pool=pool[pool.Team.isin(market['teams'])].reset_index(drop=True);active_pool.attrs=pool.attrs
   engine=PregameEngine(active_pool,[market],base,platform=full.platform,parallel=False)
   _,gr=engine.games[0];size=max(len(g[0]) for g in gr)
   means=np.zeros((2,size));splits=np.tile([base.three_share,base.make_two,base.make_three,base.make_free_throw],(2*size,1));fouls=np.full(2*size,.09)
   for t,(idx,mins,_) in enumerate(gr):
    names=[name_key(v) for v in engine.pool.loc[idx,'Name']];sp,_,fr=prior.for_names(names);means[t,:len(idx)]=mins;splits[t*size:t*size+len(idx)]=sp;fouls[t*size:t*size+len(idx)]=fr
   latest={}
   def hooked(*a,**kw):
    value=challenger_game(*a,**kw,shooting=splits,target_minutes=means,foul_rates=fouls,blowout=True);latest.clear();latest.update(value);return value
   try:
    with patch('simmah_nba_pregame.simulate_game',hooked),patch('simmah_nba_projection_anchor.simulate_game',hooked),patch('simmah_nba_markets.simulate_game',hooked):
     engine(128,81231+gi);values=engine(draws,99017+gi)
    truth=forecasts[(forecasts.package.astype(str)==package)&forecasts.team.map(canon).isin(market['teams'])]
    idmap={v:i for i,v in enumerate(engine.pool['Player ID'])}
    minute_values=np.zeros_like(values)
    for t,(idx,_,_) in enumerate(gr):minute_values[:,idx]=latest['player_minutes'][:,t*size:t*size+len(idx)]
    for _,row in truth.iterrows():
     idx=idmap[row.player_id];lo,hi=np.quantile(values[:,idx],[.1,.9])
     graded.append({'package':package,'platform':row.platform,'game_id':str(row.game_id),'player_id':row.player_id,'actual':float(row.actual),
      'baseline_covered':bool(row.p10<=row.actual<=row.p90),'challenger_covered':bool(lo<=row.actual<=hi),'baseline_mean':float(row['mean']),
      'challenger_mean':float(values[:,idx].mean()),'challenger_p10':float(lo),'challenger_p90':float(hi),'baseline_width':float(row.p90-row.p10),
      'challenger_width':float(hi-lo),'minutes_error_over5':bool(abs(row.projected_minutes-row.actual_minutes)>5),
      'actual_minutes':float(row.actual_minutes),'baseline_projected_minutes':float(row.projected_minutes),'challenger_mean_minutes':float(minute_values[:,idx].mean())})
    forecast_diag['games'].append({'teams':market['teams'],'status':'simulated','engine_reports':engine.last_report,'foulout_player_trials':int(np.isfinite(latest['disqualified_at_seconds']).sum()),'unresolved_ot':int(latest['requires_overtime'].sum())})
   except (ValueError,RuntimeError) as exc:forecast_diag['games'].append({'teams':market['teams'],'status':'failed','reason':str(exc)})
  forecast_diagnostics.append(forecast_diag)
  pd.DataFrame(graded).to_csv(out/'forecast-regrade.csv',index=False);(out/'forecast-diagnostics.json').write_text(json.dumps(forecast_diagnostics,indent=2))
  print('forecast',package,'graded',sum(r['package']==package for r in graded),flush=True)
 summarize_existing(out)

def summarize_existing(out):
 out=Path(out);frame=pd.read_csv(out/'forecast-regrade.csv')
 summary={'draws':512,'forecast_rows':len(frame),'expected_baseline_rows':1008,'forecast_results':{},'live_enabled':False}
 def stats(f):
  return {'n':len(f),'baseline_coverage':float(f.baseline_covered.mean()),'challenger_coverage':float(f.challenger_covered.mean()),'baseline_mae':float(abs(f.baseline_mean-f.actual).mean()),'challenger_mae':float(abs(f.challenger_mean-f.actual).mean()),'baseline_interval_width':float(f.baseline_width.mean()),'challenger_interval_width':float(f.challenger_width.mean()),'baseline_minutes_mae':float(abs(f.baseline_projected_minutes-f.actual_minutes).mean()),'challenger_minutes_mae':float(abs(f.challenger_mean_minutes-f.actual_minutes).mean())}
 for site,f in frame.groupby('platform'):summary['forecast_results'][site]=stats(f)
 summary['minutes_miss_over5']=stats(frame[frame.minutes_error_over5])
 summary['limitations']=['Four pregame dates, not a 227-game forecast holdout','Original baseline 10000 draws versus challenger 512; no significance claim','Shared games and repeated players create dependent observations','Conditional mechanics are evaluated separately by replay_nba_conditional_distributions.py']
 diagnostics=json.loads((out/'forecast-diagnostics.json').read_text())
 summary['calibrated_game_site_replays']=sum(g['status']=='simulated' for p in diagnostics for g in p['games'])
 summary['market_guard_misses']=sum(not r['calibration']['within_four_points'] for p in diagnostics for g in p['games'] if g['status']=='simulated' for r in g['engine_reports'] if r['calibration']['applied'])
 summary['unresolved_forecast_ot_trials']=sum(g.get('unresolved_ot',0) for p in diagnostics for g in p['games'])
 (out/'forecast-summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('evidence');p.add_argument('output');p.add_argument('--draws',type=int,default=512);a=p.parse_args();run(a.root,a.evidence,a.output,a.draws)
