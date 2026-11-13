"""Summarize a frozen 145-game, timing-only restart ablation."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from summarize_nba_possession_reconciliation import aggregate

def run(workspace):
 root=Path(workspace);out=root/'nba-restart-results';out.mkdir(exist_ok=True)
 prior=json.loads((root/'nba-possession-results/reconciliation-summary.json').read_text());clean=set(prior['clean_game_ids'])
 rows=[];failures=[]
 for p in sorted(root.glob('nba-restart-shard-*/possession-replays.json')):
  r=json.loads(p.read_text());rows+=r['results'];failures+=r['failures']
 if failures:raise ValueError(str(failures))
 if len(rows)!=145 or {r['game_id'] for r in rows}!=clean:raise ValueError('Expected exactly 145 frozen IDs, got '+str(len(rows)))
 for r in rows:
  if r['restart_training']['before']!=r['date']:raise ValueError('Wrong cutoff')
 new=aggregate(rows);observed=prior['slices']['clean_145']['actual'];old=prior['slices']['clean_145']['shooting_fouls_and_rebounds']
 summary={'games':145,'draws_per_game':128,'failures':failures,'live_enabled':False,'shooting_parameters_changed':False,'dreb_and_turnover_samplers_changed':False,'late_clock_penalty_added':False,'max_clock_partition_error':max(r['max_clock_partition_error'] for r in rows),'actual':observed,'before':old,'after':new,'remaining_possession_error':new['possessions']-observed['possessions'],'remaining_ortg_error':new['ortg']-observed['ortg'],'games_with_no_period_start_history':[r['game_id'] for r in rows if not r['restart_training']['counts']['period_start']]}
 (out/'restart-replays.json').write_text(json.dumps(rows,indent=2));(out/'restart-summary.json').write_text(json.dumps(summary,indent=2))
 print(json.dumps({k:v for k,v in summary.items() if k not in ['actual','before','after']},indent=2))
 for name,arm in [('actual',observed),('before',old),('after',new)]:
  print(name,{k:round(arm[k],4) for k in ['possessions','points','fga','fta','ortg','efg_percent','seconds_per_counted_possession']});print('durations',arm['completed_duration_by_start'])
if __name__=='__main__':run(*sys.argv[1:])
