"""Prior-date saved-PBP foul intensities and offline minutes coupling diagnostic."""
import argparse,json,gzip,zipfile,sys
from pathlib import Path
from collections import defaultdict
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_nba_mechanics_offline import simulate_minutes_fouls

def run(root,output):
 cutoff='2026-11-06';totals=defaultdict(lambda:np.zeros(2));games=[]
 for path in sorted((Path(root)/'data/nba_pbp').glob('*/*.json.gz')):
  game=json.loads(gzip.decompress(path.read_bytes()))
  if game['date']>=cutoff:continue
  events=game['events']
  if not events or events[-1]['homeScore']!=game['home_score'] or events[-1]['awayScore']!=game['away_score']:raise ValueError('Score integrity failure')
  games.append(game['event_id'])
  for team in game['boxscore']['players']:
   for section in team['statistics']:
    for player in section['athletes']:
     stats=dict(zip(section['names'],player.get('stats',[])))
     if player.get('didNotPlay') or not stats or stats.get('MIN') in (None,'','--'):continue
     m=str(stats['MIN']).split(':');minutes=float(m[0])+(float(m[1])/60 if len(m)>1 else 0)
     totals[str(player['athlete']['id'])]+=np.array([float(stats['PF']),minutes])
 league=sum(v[0] for v in totals.values())/sum(v[1] for v in totals.values())
 rates={pid:float((v[0]+120*league)/(v[1]+120)) for pid,v in totals.items()}
 # Controlled eight-player roster demonstrates coupling; it is not a saved-slate
 # forecast and its minute SD is an explicit assumption, not a fitted residual SD.
 rate=np.quantile(list(rates.values()),[.1,.25,.5,.75,.9,.25,.5,.75]);means=[36]*5+[20]*3
 trial=simulate_minutes_fouls(means,[5]*8,rate,128,83)
 result={'before':cutoff,'training_game_ids':games,'training_games':len(games),'league_personal_fouls_per_player_minute':league,
  'player_foul_rates':rates,'shrinkage_player_minutes':120,'live_enabled':False,
  'harness':{'trials':128,'team_minutes_min':float(trial['minutes'].sum(axis=1).min()),'team_minutes_max':float(trial['minutes'].sum(axis=1).max()),
  'foulout_player_trials':int(np.isfinite(trial['disqualified_at_seconds']).sum()),'max_personal_fouls':int(trial['fouls'].max()),
  'minutes_sd_by_player':trial['minutes'].std(axis=0).tolist()},
  'limitations':['Date cutoff enforced; archive lacks explicit competition labels, so these are provisional pooled priors, not promotion-ready rates',
  'Foul hazard assumes independent opportunities per six-second interval; no shot-specific or referee model',
  'Controlled roster uses assumed five-minute uncertainty, not learned pregame forecast residuals',
  'Full scoring/clock/OT integration and fresh distribution validation remain required']}
 Path(output).write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k not in ['player_foul_rates','training_game_ids']},indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('output');a=p.parse_args();run(a.root,a.output)
