import sys,json,time,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
parser=argparse.ArgumentParser(description='Same-slate FD field diagnostic; not holdout validation')
for option in ['players','standings','old-field','history','salary-history','cache-root','output']:
    parser.add_argument('--'+option,required=True)
parser.add_argument('--seed',type=int,default=123)
args=parser.parse_args()
import numpy as np,pandas as pd
from simmah_simulation_store import prepare_simulations
from simmah_classic_field import build_full_roster_field
from simmah_field_construction import learned_construction_distribution
from simmah_contest_history import matching_profiles,calibrate_field
pool=pd.read_csv(args.players)
slots=['QB','RB1','RB2','WR1','WR2','WR3','TE','FLEX','D']
steps=[-1]
def progress(f,t):
 step=int(f*10)
 if step>steps[0]:print(round(f*100),t,flush=True);steps[0]=step
start=time.perf_counter()
bundle=prepare_simulations(pool,{},'FanDuel',args.cache_root,count=10000,correlation_strength=1.,weather_by_team={},progress=progress)
pool['MeanPoints']=pool.Name.map(bundle['evaluation'].mean())
# Exact fallback from opponent_field_selection_weights, with no archived ownership.
from simmah_field_popularity import estimated_field_weights
weights=estimated_field_weights(pool,pool.MeanPoints.to_numpy(float));weights/=weights.sum()
profiles=matching_profiles(json.load(open(args.history)),'FanDuel','Full Roster',fee=.25,max_entries=150,roster_size=9,game_count=10)
assert profiles
mix=learned_construction_distribution(profiles)
salary=json.load(open(args.salary_history))['salary_counts']
rng=np.random.default_rng(args.seed);mark=time.perf_counter()
proposals=build_full_roster_field(pool,weights,slots,15000,rng=rng,platform='FanDuel',salary_counts=salary,construction_distribution=mix)
print('Generated',len(proposals),'fresh proposals',flush=True)
field,provenance=calibrate_field(proposals,pool,slots,profiles,10000,rng)
assert len(field)==10000 and field.Salary.between(59000,60000).all()
field_seconds=time.perf_counter()-mark
# Actual scores are read only after field generation and selection are finished.
actual=pd.read_csv(args.standings,low_memory=False)
players=actual[actual.Player.notna() & actual.FPTS.notna()].copy();players['Name']=players.Player.str.replace(r' \(135326-\d+\)$','',regex=True)
assert not players.Name.duplicated().any()
score_map=players.set_index('Name').FPTS.to_dict()
def score_summary(f):
 mapped=f[slots].apply(lambda c:c.map(score_map));complete=mapped.notna().all(axis=1);v=mapped.loc[complete].sum(axis=1)
 return {'entries':len(f),'scoreable':int(complete.sum()),'missing_actual_entries_excluded':int((~complete).sum()),'mean':float(v.mean()),'top10_cutoff':float(v.quantile(.9)),'top1_cutoff':float(v.quantile(.99))}
old=pd.read_csv(args.old_field)
source_scores=pd.to_numeric(actual.Points,errors='coerce').dropna()
own_actual=players.set_index('Name')['%Drafted'].str.rstrip('%').astype(float)
def ownership(f):return f[slots].stack().value_counts()/len(f)*100
new_own=ownership(field);old_own=ownership(old)
names=own_actual[own_actual>=5].index
errors=pd.DataFrame({'actual':own_actual,'old':old_own,'new':new_own}).fillna(0)
comparison={n:{k:float(v) for k,v in errors.loc[n].items()} for n in ['Isaiah Likely','Matthew Stafford','Tampa Bay Buccaneers','D\'Andre Swift','Puka Nacua']}
report={'scope':'Same-slate diagnostic, not holdout or exact original app replay. Anonymous construction profile was trained on this contest. No archived pregame ownership, roles or weather: current engine defaults, neutral weather and projection/value ownership fallback used. Actual player scores loaded only after lineup selection.','seed':args.seed,'model_preparation_key':bundle['metadata']['key'],'player_pool':len(pool),'fresh_proposals':len(proposals),'final_opponents':len(field),'field_seconds':field_seconds,'total_seconds':time.perf_counter()-start,'calibration':provenance,'proposal_actual_scores':score_summary(proposals),'old':score_summary(old),'new':score_summary(field),'real':{'entries':len(actual),'scored_entries':len(source_scores),'mean':float(source_scores.mean()),'top10_cutoff':float(source_scores.quantile(.9)),'top1_cutoff':float(source_scores.quantile(.99))},'ownership_examples':comparison,'ownership_mae_for_actual_at_least_5_percent':{'players':len(names),'old':float((errors.loc[names,'old']-errors.loc[names,'actual']).abs().mean()),'new':float((errors.loc[names,'new']-errors.loc[names,'actual']).abs().mean())},'joint_construction_counts':np.bincount(field['Construction Group'],minlength=6).tolist()}
Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2),flush=True)
