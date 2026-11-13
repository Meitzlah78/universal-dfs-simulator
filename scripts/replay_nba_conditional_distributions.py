"""227-game conditional pace/FTA/ceiling diagnostics; never a pregame backtest."""
import json,gzip,zipfile,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from replay_nba_full_game_offline import actual_rows,Priors,rotations,EventRates,baseline_game,challenger_game
from simmah_nba_scoring import score_nba
from simmah_nba_baseline_audit_offline import simulate_game as baseline_game

def run(root,evidence,output):
 root=Path(root);out=Path(output);out.mkdir(exist_ok=True)
 with zipfile.ZipFile(next(Path(evidence).glob('Simmah_NBA_Comprehensive_Audit*.zip'))) as z:ids={v['game_id'] for v in json.loads(z.read('pbp-audit.json'))['inventory']}
 games=[]
 for path in sorted((root/'data/nba_pbp').glob('*/*.json.gz')):
  g=json.loads(gzip.decompress(path.read_bytes()))
  if g['event_id'] in ids:games.append(g)
 games.sort(key=lambda g:(g['date'],g['event_id']))
 base=EventRates(**json.loads((root/'data/nba_models/event-rates-before-2026-04-09.json').read_text())['rates'])
 metrics=[];ceilings=[]
 for gi,g in enumerate(games):
  players=actual_rows(g);teams=list(dict.fromkeys(r['team'] for r in players));by=[[r for r in players if r['team']==t and r['v'][0]>0] for t in teams]
  try:
   if len(teams)!=2 or min(map(len,by))<5:raise ValueError('Observed floor support missing')
   size=max(map(len,by));means=np.zeros((2,size));profiles=np.zeros((2,size,5));splits=np.tile([base.three_share,base.make_two,base.make_three,base.make_free_throw],(size*2,1));fouls=np.full(size*2,.09)
   prior=Priors(games,g['date'],base)
   for t,group in enumerate(by):
    raw=np.array([r['v'][0] for r in group]);means[t,:len(group)]=raw*240/raw.sum()
    sp,roles,fr=prior.for_names([r['name'] for r in group]);profiles[t,:len(group)]=roles;splits[t*size:t*size+len(group)]=sp;fouls[t*size:t*size+len(group)]=fr
   reg,ot=rotations(means,128,71+gi*17)
   old=baseline_game(reg,profiles,[base]*2,33+gi,ot)
   new=challenger_game(reg,profiles,[base]*2,33+gi,ot,shooting=splits,target_minutes=means,foul_rates=fouls,blowout=True)
   actual_fga=sum(r['v'][2] for r in players);actual_fta=sum(r['v'][6] for r in players);actual_orb=0
   for team in g['boxscore']['teams']:
    ts={v['name']:v['displayValue'] for v in team['statistics']};actual_orb+=float(ts.get('offensiveRebounds',0))
   actual_to=sum(r['to'] for r in players)
   old_fga=old['counters']['field_goal_makes']+old['counters']['field_goal_misses'];new_fga=new['attempts'][:,:,0].sum(axis=1)
   old_fta=old['stats'][:,:,2].sum(axis=1)+old['counters']['free_throw_misses'];new_fta=new['attempts'][:,:,2].sum(axis=1)
   def describe(v):return {'mean':float(np.mean(v)),'p10':float(np.quantile(v,.1)),'p90':float(np.quantile(v,.9)),'p95':float(np.quantile(v,.95))}
   # Approximate team possessions; field goals/FTA are per game over both teams.
   # Standard .44 formula is a proxy, not reconstructed event possession count.
   old_possessions=(old_fga+.44*old_fta-old['counters']['offensive_rebounds']+old['counters']['turnovers'])/2
   new_possessions=(new_fga+.44*new_fta-new['mechanics_counters']['offensive_rebounds']+new['counters']['turnovers']+new['mechanics_counters']['shot_clock_violations'])/2
   rec={'game_id':g['event_id'],'date':g['date'],'status':'simulated','actual_fga_player_sum':actual_fga,'actual_fta':actual_fta,
        'actual_points':g['home_score']+g['away_score'],'actual_approx_possessions_per_team':(actual_fga+.44*actual_fta-actual_orb+actual_to)/2,
        'baseline_possessions_proxy':describe(old_possessions),'challenger_possessions_proxy':describe(new_possessions),'baseline_fga':describe(old_fga),'challenger_fga':describe(new_fga),'baseline_fta':describe(old_fta),'challenger_fta':describe(new_fta),
        'baseline_points':describe(old['team_points'].sum(axis=1)),'challenger_points':describe(new['team_points'].sum(axis=1)),
        'challenger_fta_80_covered':bool(np.quantile(new_fta,.1)<=actual_fta<=np.quantile(new_fta,.9)),
        'baseline_fta_80_covered':bool(np.quantile(old_fta,.1)<=actual_fta<=np.quantile(old_fta,.9)),
        'challenger_unresolved_ot':int(new['requires_overtime'].sum())}
   metrics.append(rec)
   for t,group in enumerate(by):
    for k,row in enumerate(group):
     # Observed >=30-minute cohort is a conditional ceiling diagnostic, not a
     # pregame star classifier. The actual minutes are supplied to BOTH arms.
     if row['v'][0]<30:continue
     idx=t*size+k;actual=float(score_nba('FanDuel',**row['actual']));op90,op95=np.quantile(old['scores'][:,idx],[.9,.95]);np90,np95=np.quantile(new['scores'][:,idx],[.9,.95])
     ceilings.append({'game_id':g['event_id'],'player_id':row['id'],'actual_fd':actual,'baseline_p90':float(op90),'baseline_p95':float(op95),'challenger_p90':float(np90),'challenger_p95':float(np95)})
  except (ValueError,RuntimeError) as exc:metrics.append({'game_id':g['event_id'],'status':'failed','reason':str(exc)})
  if gi%25==0 or gi==len(games)-1:
   (out/'conditional-distributions.json').write_text(json.dumps(metrics,indent=2));(out/'conditional-ceilings.json').write_text(json.dumps(ceilings,indent=2));print('distributions',gi+1,'/',len(games),flush=True)
 good=[r for r in metrics if r['status']=='simulated'];summary={'games_attempted':len(metrics),'games_completed':len(good),'draws':128,'live_enabled':False,
  'actual_mean_points':float(np.mean([r['actual_points'] for r in good])),'actual_mean_fga_player_sum':float(np.mean([r['actual_fga_player_sum'] for r in good])),
  'actual_mean_fta':float(np.mean([r['actual_fta'] for r in good])),'actual_approx_possessions_per_team':float(np.mean([r['actual_approx_possessions_per_team'] for r in good])),
  'mean_outputs':{arm:{key:float(np.mean([r[arm+'_'+key]['mean'] for r in good])) for key in ['points','fga','fta','possessions_proxy']} for arm in ['baseline','challenger']},
  'fta_80_coverage':{arm:float(np.mean([r[arm+'_fta_80_covered'] for r in good])) for arm in ['baseline','challenger']},
  'conditional_30plus_minute_cohort':{'n':len(ceilings),**{arm:{'above_p90':float(np.mean([r['actual_fd']>r[arm+'_p90'] for r in ceilings])),'above_p95':float(np.mean([r['actual_fd']>r[arm+'_p95'] for r in ceilings]))} for arm in ['baseline','challenger']}},
  'limitations':['Both arms use observed rosters and normalized observed minutes; no predictive star/player/minutes calibration claim','128 draws per game: quantiles are approximate; shared games create dependent player observations','Historical shot/rate priors use earlier dates only; no current game scoring fitted','FGA proxy screens volume; shot-count reconciliation and team-heave conventions prevent treating it as exact pace','Possessions use FGA+.44FTA-OREB+TO per team, a box-score proxy rather than exact event reconstruction']}
 (out/'conditional-distribution-summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
if __name__=='__main__':run(*sys.argv[1:])
