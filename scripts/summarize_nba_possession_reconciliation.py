"""Matched-slice possession and Four-Factors audit; no live integration."""
import json,sys
from pathlib import Path
from collections import Counter,defaultdict
import numpy as np
from audit_nba_clock import load
from simmah_nba_possession_trace_offline import reconstruct_trace,kind


def source_row(game,trace):
 row=dict(game_id=game['event_id'],date=game['date'],points=game['home_score']+game['away_score'],possessions=len(trace['possessions']),elapsed=2880+300*max(0,max(int(e['period']['number']) for e in game['events'])-4))
 for key in ['fgm','fga','three_pm','three_pa','ftm','fta','player_oreb','player_dreb','turnovers']:row[key]=0
 for team in game['boxscore']['teams']:
  s={v['name']:v['displayValue'] for v in team['statistics']}
  for field,made,attempt in [('fieldGoalsMade-fieldGoalsAttempted','fgm','fga'),('threePointFieldGoalsMade-threePointFieldGoalsAttempted','three_pm','three_pa'),('freeThrowsMade-freeThrowsAttempted','ftm','fta')]:
   m,a=map(int,s[field].split('-'));row[made]+=m;row[attempt]+=a
  row['player_oreb']+=int(s['offensiveRebounds']);row['player_dreb']+=int(s['defensiveRebounds']);row['turnovers']+=int(s['totalTurnovers'])
 row['origin_counts']={};row['origin_seconds']={};row['terminal_counts']={};row['terminal_seconds']={}
 row['oreb_tails']=0;row['oreb_tail_seconds']=0
 for p in trace['possessions']:
  if p['usable'] and p['completed']:
   k=p['origin'];row['origin_counts'][k]=row['origin_counts'].get(k,0)+1;row['origin_seconds'][k]=row['origin_seconds'].get(k,0)+p['seconds']
  elif p['usable']:
   k=p['origin'];row['terminal_counts'][k]=row['terminal_counts'].get(k,0)+1;row['terminal_seconds'][k]=row['terminal_seconds'].get(k,0)+p['seconds']
  if p['usable']:
   row['oreb_tails']+=len(p['oreb_tail_seconds']);row['oreb_tail_seconds']+=sum(p['oreb_tail_seconds'])
 row['trace_clock_error']=sum(p['seconds'] for p in trace['possessions'])-row['elapsed']
 return row


def aggregate(rows):
 def total(k):return sum(r[k] for r in rows)
 n=len(rows);p=total('possessions');fga=total('fga');fta=total('fta');to=total('turnovers');o=total('player_oreb');d=total('player_dreb')
 out={'games':n,**{k:total(k)/n for k in ['points','possessions','elapsed','fga','three_pa','fta','fgm','three_pm','ftm','turnovers','player_oreb','player_dreb']},
 'team_pace_per_48':p*.5*2880/total('elapsed'),'ortg':100*total('points')/p,'efg_percent':100*(total('fgm')+.5*total('three_pm'))/fga,
 'tov_percent_per_possession':100*to/p,'tov_percent_box_exposure':100*to/(fga+.44*fta+to),'oreb_percent':100*o/(o+d),'ftr':fta/fga,
 'three_attempt_share_percent':100*total('three_pa')/fga,'two_percent':100*(total('fgm')-total('three_pm'))/(fga-total('three_pa')),'three_percent':100*total('three_pm')/total('three_pa'),'ft_percent':100*total('ftm')/fta,
 'seconds_per_counted_possession':total('elapsed')/p,'box_possession_proxy_per_game':(fga+.44*fta-o+to)/n}
 counts=Counter();seconds=Counter();terminal=Counter();terminal_seconds=Counter()
 for r in rows:
  if 'origins' in r:
   counts.update(dict(zip(r['origins'],r['completed_counts'])));seconds.update(dict(zip(r['origins'],r['completed_seconds'])));terminal.update(dict(zip(r['origins'],r['terminal_counts'])));terminal_seconds.update(dict(zip(r['origins'],r['terminal_seconds'])))
  else:counts.update(r['origin_counts']);seconds.update(r['origin_seconds']);terminal.update(r['terminal_counts']);terminal_seconds.update(r['terminal_seconds'])
 out['completed_duration_by_start']={k:{'count_per_game':v/n,'mean_seconds':seconds[k]/v} for k,v in sorted(counts.items()) if v}
 out['terminal_duration_by_start']={k:{'count_per_game':v/n,'mean_seconds':terminal_seconds[k]/v} for k,v in sorted(terminal.items()) if v}
 out['oreb_continuation_tail_seconds']=total('oreb_tail_seconds')/total('oreb_tails');out['oreb_continuation_tails_per_game']=total('oreb_tails')/n
 return out


def summarize(root,evidence,results):
 out=Path(results);games,allowed=load(root,evidence);games=[g for g in games if g['event_id'] in allowed]
 traces=[reconstruct_trace(g) for g in games];(out/'source-traces.json').write_text(json.dumps(traces,indent=2))
 clean={t['game_id'] for t in traces if not t['flags'] and not t['issues']};source=[source_row(g,t) for g,t in zip(games,traces)]
 turnover_mismatches=[]
 for g,r in zip(games,source):
  n=sum(kind(e) in ['turnover','violation'] for e in g['events'])
  if n!=r['turnovers']:turnover_mismatches.append({'game_id':g['event_id'],'event_turnovers':n,'official_turnovers':r['turnovers'],'boundary_clean':g['event_id'] in clean})
 records=[];failures=[]
 for p in sorted(out.parent.glob('nba-possession-shard-*/possession-replays.json')):
  x=json.loads(p.read_text());records+=x['results'];failures+=x['failures']
 if failures:raise ValueError(str(failures[:3]))
 keys={(r['game_id'],r['arm']) for r in records}
 if len(keys)!=len(records):raise ValueError('Duplicate replay rows')
 arms=['clock_reference','shooting_fouls_and_rebounds']
 if keys!={(g['event_id'],a) for g in games for a in arms}:raise ValueError('Incomplete frozen replay set '+str(len(keys)))
 old=json.loads((out.parent/'nba-hazard-resume/hazard-replays.json').read_text());prior={(r['game_id'],r['arm']):r for r in old['results']}
 delta=max(abs(r[k]-prior[(r['game_id'],r['arm'])][k]) for r in records for k in ['points','fga','fta','player_oreb','player_dreb'])
 if delta>1e-12:raise ValueError('Instrumentation altered original draws: '+str(delta))
 report={'status':'offline diagnostic only','draws_per_game_arm':128,'replay_records':len(records),'failures':failures,'raw_output_max_difference_vs_previous_hazard_replay':delta,'max_simulated_possession_clock_partition_error':max(r['max_clock_partition_error'] for r in records),'source_scoring_mismatches':[t['game_id'] for t in traces if t['reconciled_points']!=t['official_points']],'clean_game_ids':sorted(clean),'flagged_game_ids':sorted(allowed-clean),'source_flags':dict(sum((Counter(t['flags']) for t in traces),Counter())),'source_max_abs_trace_clock_error':max(abs(r['trace_clock_error']) for r in source),'clean_source_max_abs_trace_clock_error':max(abs(r['trace_clock_error']) for r in source if r['game_id'] in clean),'source_turnover_reconciliation_mismatches':turnover_mismatches,'slices':{}}
 for name,ids in [('clean_145',clean),('full_226_provisional_possessions',allowed),('clean_box_turnover_matched_sensitivity',clean-{r['game_id'] for r in turnover_mismatches})]:
  a=aggregate([r for r in source if r['game_id'] in ids]);s={'actual':a}
  for arm in arms:
   b=aggregate([r for r in records if r['game_id'] in ids and r['arm']==arm]);s[arm]=b
   s[arm]['point_overshoot_decomposition']={'total_points_per_game':b['points']-a['points'],'pace_contribution':(b['possessions']-a['possessions'])*(b['ortg']+a['ortg'])/200,'efficiency_contribution':(b['ortg']-a['ortg'])*(b['possessions']+a['possessions'])/200}
  report['slices'][name]=s
 (out/'possession-replays.json').write_text(json.dumps({'results':records,'failures':failures},indent=2));(out/'source-box-metrics.json').write_text(json.dumps(source,indent=2));(out/'reconciliation-summary.json').write_text(json.dumps(report,indent=2))
 print(json.dumps({k:v for k,v in report.items() if k not in ['clean_game_ids','flagged_game_ids']},indent=2))
if __name__=='__main__':summarize(*sys.argv[1:])
