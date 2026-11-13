"""Grade prior-date hazard probabilities on observed exposures, not simulated scores."""
import json,sys,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from audit_nba_clock import load
from audit_nba_hazards import observe_hazards,fit_hazards
from replay_nba_full_game_offline import EventRates

def run(root,evidence,output):
 root=Path(root);games,allowed=load(root,evidence);records=[observe_hazards(g) for g in games]
 base=EventRates(**json.loads((root/'data/nba_models/event-rates-before-2026-04-09.json').read_text())['rates']);incumbent=base.free_throw_trip/(1-base.turnover-.055-.002);rows=[]
 for r in records:
  if r['game_id'] not in allowed:continue
  fit=fit_hazards(records,r['date'],base);c=r['counts'];sf=c.get('shooting_fouls',0)-c.get('verified_and_one_fouls',0);fg=c.get('fga',0);p=fit['normal_shooting_foul_probability_per_opportunity']
  def loss(q):return -sf*math.log(q)-fg*math.log1p(-q)
  rows.append({'game_id':r['game_id'],'date':r['date'],'sf_normal':sf,'fga':fg,'exposures':sf+fg,'fitted_probability':p,'baseline_probability':incumbent,'baseline_loss_sum':loss(incumbent),'fitted_loss_sum':loss(p)})
 n=sum(r['exposures'] for r in rows);slices={}
 for label,start,end in [('Oct_03_20','2026-10-03','2026-10-20'),('Oct_21_31','2026-10-21','2026-10-31'),('Nov_01_11','2026-11-01','2026-11-11')]:
  sample=[r for r in rows if start<=r['date']<=end];den=sum(r['exposures'] for r in sample)
  slices[label]={'games':len(sample),'observed_probability':sum(r['sf_normal'] for r in sample)/den,'mean_fitted_probability_exposure_weighted':sum(r['fitted_probability']*r['exposures'] for r in sample)/den}
 result={'games':len(rows),'observed_normal_foul_probability':sum(r['sf_normal'] for r in rows)/n,'baseline_probability':incumbent,'baseline_log_loss':sum(r['baseline_loss_sum'] for r in rows)/n,'fitted_log_loss':sum(r['fitted_loss_sum'] for r in rows)/n,'calendar_slices_not_verified_season_types':slices,'games_detail':rows,'live_enabled':False}
 Path(output).write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='games_detail'},indent=2))
if __name__=='__main__':run(*sys.argv[1:])
