"""Observed-support oracle diagnostic, never a pregame forecast."""
import sys,json,hashlib,time,subprocess,argparse
from pathlib import Path
import numpy as np,pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_contest_history import parse_lineups,verified_fanduel_mvp_first,name_key
from simmah_single_calibration import calibrate_role_weights,RoleDual
from simmah_single_validation import compare_fields

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--standings',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--slate-id',required=True)
parser.add_argument('--contest-id',required=True)
parser.add_argument('--expected-entries',type=int)
args=parser.parse_args()
source=args.standings;root=args.output;root.mkdir(parents=True,exist_ok=False)
f=pd.read_csv(source,low_memory=False);lineups=verified_fanduel_mvp_first(f,parse_lineups(f))
if not lineups or any(len(r)!=6 for r in lineups):raise ValueError('Six verified slots required')
if args.expected_entries is not None and len(lineups)!=args.expected_entries:raise ValueError('Parsed entry count does not match expected count')
meta=f[f.Player.notna()].copy();meta['key']=meta.Player.map(name_key)
if meta.groupby('key').Salary.nunique().max()>1:raise ValueError('Conflicting historical salaries')
meta=meta.drop_duplicates('key').set_index('key')
observed=sorted({name_key(name) for row in lineups for _,name in row})
if any(key not in meta.index for key in observed):raise ValueError('Missing historical player metadata')
# FD IDs come from the same historical export, not a later slate's IDs.
import re
ids=[]
for key in observed:
 match=re.search(r'\(([^()]+)\)\s*$',str(meta.loc[key,'Player']))
 if not match:raise ValueError('Historical player ID absent')
 ids.append(match.group(1))
if len(set(ids))!=len(ids):raise ValueError('Duplicate historical IDs')
index={key:i for i,key in enumerate(observed)}
rows=np.asarray([[index[name_key(name)] for _,name in row] for row in lineups],dtype=np.int32)
rows[:,1:]=np.sort(rows[:,1:],axis=1)
if (np.diff(np.sort(rows,axis=1),axis=1)==0).any():raise ValueError('Repeated player')
support,counts=np.unique(rows,axis=0,return_counts=True)
salary=pd.to_numeric(meta.loc[observed,'Salary'],errors='raise').to_numpy(float)
costs=salary[support].sum(axis=1)+.5*salary[support[:,0]]
if (costs>60000).any():raise ValueError('Observed roster exceeds historical assumed FD salary cap; investigate format')
w=counts/counts.sum();n=len(ids);q=np.full(len(support),1/len(support))
d=RoleDual(support,q,np.bincount(support[:,0],weights=w,minlength=n),sum(np.bincount(support[:,s],weights=w,minlength=n) for s in range(1,6)))
start=time.perf_counter();result=calibrate_role_weights(support,q,d.target[:n],d.target[n:],feasibility_seconds=15,max_iterations=2000)
seconds=time.perf_counter()-start
report=compare_fields(support,result.weights,costs,ids,support,counts,costs,ids,
 slate_id=args.slate_id,reference_slate_id=args.slate_id,site='fd',reference_site='fd',prior=q)
common={'slate_id':args.slate_id,'site':'fd','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
 'contest_id':args.contest_id,'parsed_entries':len(rows),'support_kind':'unique observed contest rosters only',
 'completeness':'Parsed supplied standings; full contest capacity was not independently verified.',
 'scope':'Oracle actual-ownership targets on observed support; not predictive validation.'}
np.savez(root/'actual_field.npz',indices=support,probabilities=counts,salary=costs,player_ids=np.array(ids),metadata_json=np.asarray(json.dumps(dict(common,source_kind='actual_contest'))))
np.savez(root/'calibrated_field.npz',indices=support,probabilities=result.weights,prior=q,salary=costs,player_ids=np.array(ids),metadata_json=np.asarray(json.dumps(dict(common,source_kind='oracle_calibrated_model'))))
summary={'entries':len(rows),'unique_observed_rosters':len(support),'players':n,'calibration_seconds':seconds,
 'diagnostics':result.diagnostics,'role_metrics':report['roles']['summary'],'all_slot_metrics':report['all_slot']['summary'],
 'salary_wasserstein_dollars':report['salary']['wasserstein_dollars'],'salary_cdf_max_abs_difference':report['salary']['cdf_max_abs_difference'],
 'metadata':common,'limitations':['Uniform prior over observed legal rosters, not independently learned construction prior.',
 'Observed-support oracle guarantees target feasibility by construction; it does not test exhaustive-universe support or unseen rosters.',
 'Same-contest actual ownership is intentionally used as an oracle target; no pregame accuracy claim.',
 'Incomplete standings may bias all observed reference statistics; supplied row count is not proof of full-field completeness.']}
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
subprocess.run([sys.executable,str(Path(__file__).resolve().with_name('validate_single_field.py')),'--sim',str(root/'calibrated_field.npz'),'--reference',str(root/'actual_field.npz'),'--output',str(root/'diagnostics.zip'),'--joint-alert-pp','5','--covariance-alert-pp','5','--salary-alert-dollars','150'],check=True,stdout=subprocess.DEVNULL)
print(json.dumps(summary,indent=2),flush=True)
