"""Compare aligned single-game NPZ fields, without changing live behavior.

Each NPZ must have indices (J,6), probabilities (J,), salary (J,), player_ids,
and metadata_json with slate_id, site and source_kind. Source kind must
identify an actual_contest or a generated_reference; they are never conflated.
"""
import argparse,hashlib,json,sys,io,zipfile,csv
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_single_validation import compare_fields


def load(path):
    raw=path.read_bytes()
    with np.load(io.BytesIO(raw),allow_pickle=False) as f:
        result={key:f[key] for key in ['indices','probabilities','salary','player_ids']}
        result['metadata']=json.loads(str(f['metadata_json'].item()))
        result['prior']=f['prior'] if 'prior' in f.files else None
    meta=result['metadata']
    if not meta.get('slate_id') or meta.get('site') not in {'dk','fd'} or not meta.get('source_kind'):
        raise ValueError('Explicit slate_id, site and source_kind metadata required')
    result['sha256']=hashlib.sha256(raw).hexdigest()
    return result


def csv_bytes(header,rows):
    out=io.StringIO(newline='');writer=csv.writer(out);writer.writerow(header);writer.writerows(rows)
    return out.getvalue().encode()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sim',type=Path,required=True);p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True,help='New diagnostics ZIP')
    p.add_argument('--joint-alert-pp',type=float)
    p.add_argument('--covariance-alert-pp',type=float)
    p.add_argument('--salary-alert-dollars',type=float)
    a=p.parse_args()
    if a.output.exists():raise ValueError('Refusing to overwrite output')
    for threshold in (a.joint_alert_pp,a.covariance_alert_pp,a.salary_alert_dollars):
        if threshold is not None and (not np.isfinite(threshold) or threshold<0):raise ValueError('Alert thresholds must be finite and nonnegative')
    sim=load(a.sim);ref=load(a.reference);sm=sim['metadata'];rm=ref['metadata']
    if rm['source_kind'] not in {'actual_contest','generated_reference'}:raise ValueError('Reference must identify actual_contest or generated_reference')
    r=compare_fields(sim['indices'],sim['probabilities'],sim['salary'],sim['player_ids'].tolist(),
        ref['indices'],ref['probabilities'],ref['salary'],ref['player_ids'].tolist(),
        slate_id=sm['slate_id'],reference_slate_id=rm['slate_id'],site=sm['site'],reference_site=rm['site'],prior=sim['prior'])
    n=len(r['player_ids']);labels=[(v['player_id'],v['role']) for v in r['column_mapping']]
    files={'column_mapping.json':json.dumps(r['column_mapping'],indent=2).encode()}
    for name in ('roles','all_slot'):
        data=r[name];mapping=labels if name=='roles' else [(key,'ANY') for key in r['player_ids']]
        pair_rows=[]
        for i in range(len(mapping)):
            for j in range(i+1,len(mapping)):
                if name=='roles' and ((i<n and j<n) or (i<n and j==n+i)):continue
                pair_rows.append([*mapping[i],*mapping[j],data['simulated']['joint'][i,j],data['reference']['joint'][i,j],
                    data['joint_residual'][i,j]*100,data['covariance_residual'][i,j]*100])
        pair_rows.sort(key=lambda row:abs(row[-2]),reverse=True)
        files[name+'_pair_residuals.csv']=csv_bytes(['player_a','role_a','player_b','role_b','sim_joint_probability',
            'reference_joint_probability','joint_residual_pp','covariance_residual_pp'],pair_rows)
        arrays=io.BytesIO();np.savez(arrays,sim_joint=data['simulated']['joint'],reference_joint=data['reference']['joint'],
            joint_residual=data['joint_residual'],covariance_residual=data['covariance_residual'])
        files[name+'_matrices.npz']=arrays.getvalue()
    salary=r['salary']
    for label in ('simulated','reference'):
        d=salary[label];files[label+'_salary_distribution.csv']=csv_bytes(['salary','probability','cdf'],zip(d['salary'],d['mass'],d['cdf']))
    alerts=[]
    # The cross-section uses special/FLEX pairs only, excluding same-player exclusion.
    cross=r['roles']['covariance_residual'][:n,n:];mask=~np.eye(n,dtype=bool)
    crossmax=float(np.max(np.abs(cross[mask]))*100)
    if a.joint_alert_pp is not None and r['roles']['summary']['pair_max_abs_pp']>a.joint_alert_pp:alerts.append('Role-pair joint residual exceeds configured exploratory threshold')
    if a.covariance_alert_pp is not None and crossmax>a.covariance_alert_pp:alerts.append('CPT/MVP-FLEX covariance exceeds configured exploratory threshold')
    if a.salary_alert_dollars is not None and salary['wasserstein_dollars']>a.salary_alert_dollars:alerts.append('Salary Wasserstein exceeds configured exploratory threshold')
    kl=r['kl_from_prior']
    summary={'offline_only':True,'slate_id':r['slate_id'],'site':r['site'],'reference_kind':rm['source_kind'],
        'kl_from_prior':kl if kl is None or np.isfinite(kl) else None,'kl_infinite':bool(kl is not None and np.isinf(kl)),
        'role_metrics':r['roles']['summary'],'all_slot_metrics':r['all_slot']['summary'],
        'salary_wasserstein_dollars':salary['wasserstein_dollars'],'salary_cdf_max_abs_difference':salary['cdf_max_abs_difference'],
        'salary_quantiles':{key:salary[key]['quantiles'] for key in ('simulated','reference')},
        'special_flex_covariance_max_abs_pp':crossmax,'alerts':alerts,
        'thresholds':{'joint_alert_pp':a.joint_alert_pp,'covariance_alert_pp':a.covariance_alert_pp,'salary_alert_dollars':a.salary_alert_dollars},
        'provenance':{'sim':sm,'reference':rm},'input_sha256':{'sim':sim['sha256'],'reference':ref['sha256']},
        'limitations':['Configured alerts are exploratory, not validated pass/fail gates.',
        'Covariance removes the product-of-marginals component but is not invariant to marginals or across slates.',
        'Neither matching ownership nor low KL or pair error proves predictive profitability.']}
    files['summary.json']=(json.dumps(summary,indent=2,allow_nan=False)+'\n').encode()
    files['hashes.json']=json.dumps({name:hashlib.sha256(raw).hexdigest() for name,raw in files.items()},indent=2).encode()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('xb') as handle:
        with zipfile.ZipFile(handle,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for name,raw in files.items():z.writestr(name,raw)
    print(json.dumps(summary,indent=2,allow_nan=False))

if __name__=='__main__':main()
