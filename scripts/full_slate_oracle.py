import sys,json,time,hashlib,argparse
from pathlib import Path
import numpy as np,pandas as pd
from scipy.stats import wasserstein_distance
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_single_partition import SalaryPartition
from simmah_single_calibration import RoleDual
from simmah_single_validation import joint_probabilities
from simmah_single_exhaustive import enumerate_lineups
parser=argparse.ArgumentParser(description='Offline full-site-slate oracle. No live behavior changes.')
parser.add_argument('--slate-csv',type=Path,required=True,help='Normalized original-site player list: Id, Nickname, Salary, MVP 1.5x Salary, Team')
parser.add_argument('--actual-field',type=Path,required=True)
parser.add_argument('--slate-id',required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
root=args.output;root.mkdir(parents=True,exist_ok=False)
pool=pd.read_csv(args.slate_csv,keep_default_na=False)
if pool.Id.duplicated().any() or not pool.Id.astype(str).str.startswith(args.slate_id+'-').all():raise ValueError('Invalid or wrong-slate site IDs')
ids=pool.Id.tolist();index={key:i for i,key in enumerate(ids)}
with np.load(args.actual_field,allow_pickle=False) as f:
 actual_meta=json.loads(str(f['metadata_json'].item()))
 if actual_meta.get('slate_id')!=args.slate_id or actual_meta.get('site')!='fd' or actual_meta.get('source_kind')!='actual_contest':raise ValueError('Same-slate actual FD reference required')
 oldids=f['player_ids'].tolist();mapping=np.array([index[i] for i in oldids]);rows=mapping[f['indices']];counts=f['probabilities'];historicalcost=f['salary']
salary=pool.Salary.to_numpy(int);special=pool['MVP 1.5x Salary'].to_numpy(int);teams=pool.Team.to_numpy();n=len(ids)
cost=special[rows[:,0]]+salary[rows[:,1:]].sum(axis=1)
assert np.array_equal(cost,historicalcost)
legal=(cost<=60000)&(teams[rows]!=teams[rows[:,0,None]]).any(axis=1)&(np.diff(np.sort(rows,axis=1),axis=1)!=0).all(axis=1)
assert legal.all()
w=counts/counts.sum();ct=np.bincount(rows[:,0],weights=w,minlength=n);ft=sum(np.bincount(rows[:,i],weights=w,minlength=n) for i in range(1,6))
# HiGHS solves on an explicit contained subset. Its witness remains a valid
# certificate on the complete legal universe by assigning zero to other rows.
d=RoleDual(rows,np.ones(len(rows)),ct,ft);feasible=d.feasibility(time_limit=15)
print('HiGHS feasible certificate on contained observed subset',flush=True)
engine=SalaryPartition(salary,special,teams,60000);start=time.perf_counter();result=engine.calibrate(ct,ft,max_iterations=500)
print('Full-support fit',result['diagnostics'],'seconds',time.perf_counter()-start,flush=True)
summary={'site':'fd','slate_id':args.slate_id,'site_players':n,'observed_players':len(oldids),'unique_observed_rosters':len(rows),'observed_entries':int(counts.sum()),
 'coverage_unique_pct':100.,'coverage_entries_pct':100.,'coverage_method':'All observed rows satisfy the same roster/salary/two-team predicates; streaming enumeration membership pending.',
 'feasibility':feasible,'feasibility_certificate_scope':'HiGHS on observed-roster subset verified contained in complete universe; extend witness with zero weights elsewhere.',
 'calibration':result['diagnostics'],'calibration_seconds':time.perf_counter()-start,
 'salary_wasserstein_dollars':float(wasserstein_distance(result['salary_axis'],cost,u_weights=result['salary_density'],v_weights=w)),
 'pool_sha256':hashlib.sha256(args.slate_csv.read_bytes()).hexdigest(),
 'source_scope':'Complete caller-provided site salary list, no injury/point filter, all MVPs, floor 0, cap 60000.',
 'limitations':['Oracle actual role targets, not a predictive ownership test.','Unobserved site players have exact zero actual targets; optimizer works on that forced-zero face while retaining the full prior normalization.',
 'KL across differently sized support universes has no universal interpretation or acceptance threshold.','No full-universe primal LP is materialized; feasibility uses a mathematically valid embedded witness.']}
np.savez(root/'partition_solution.npz',theta=result['theta'],marginal=result['marginal'],salary_density=result['salary_density'],salary_axis=result['salary_axis'],player_ids=np.asarray(ids),special_target=ct,flex_target=ft)
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');pool.to_csv(root/'site_slate.csv',index=False)
print(json.dumps(summary,indent=2),flush=True)
# Independently check actual membership with the existing NumPy enumerator.
pp=pd.DataFrame({'Player ID':ids,'Salary':salary,'Team':teams})
canonical=rows.copy();canonical[:,1:]=np.sort(canonical[:,1:],axis=1)
def packed(a):return np.ascontiguousarray(a,dtype=np.int32).view(np.dtype((np.void,24))).ravel()
lookup={v.tobytes():i for i,v in enumerate(packed(canonical))};found=np.zeros(len(rows),bool);total=0;started=time.perf_counter()
for chunk,_ in enumerate_lineups(pp,'fd',min_salary=0,batch_sets=32768):
 total+=len(chunk)
 # Search each historical key in a sorted bounded chunk, avoiding a global set.
 arr=np.sort(packed(chunk));query=packed(canonical[~found]);loc=np.searchsorted(arr,query);safe=np.minimum(loc,len(arr)-1)
 hits=(loc<len(arr))&(arr[safe]==query);missing=np.flatnonzero(~found);found[missing[hits]]=True
summary.update(enumerated_legal_rosters=total,covered_unique_rosters=int(found.sum()),coverage_unique_pct=float(found.mean()*100),coverage_entries_pct=float(counts[found].sum()/counts.sum()*100),enumeration_seconds=time.perf_counter()-started,coverage_method='Exact streamed NumPy enumeration intersection, MVP preserved and FLEX canonically sorted')
assert total==result['diagnostics']['full_support_count'];assert found.all()
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print('EXACT COVERAGE COMPLETE',total,found.sum(),time.perf_counter()-started,flush=True)
