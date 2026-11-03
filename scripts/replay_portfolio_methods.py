"""Multi-format outcome-blind portfolio replay with within-contest paired deltas.

Uses frozen legal candidates, never generates or rearranges roster slots. Saved
candidate-generation rules (positions, salary, team/stack rules) remain embodied
in those candidates. Does not invent a mandatory QB stack. Historical missing
manual settings remain a limitation of the input archive, not reconstructed fact.
"""
import argparse
import json
import math
from pathlib import Path
import sys
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parent))
from compare_portfolio_rankings import compare
from simmah_portfolio_selection import select_portfolio

PROTOCOL_VERSION='multi-format-replay-v1'


def constraints(frame,slots,count,controls):
    """Same integer hard min/max/lock/fade and role limits as shared selector."""
    names=sorted(set(frame[slots].astype(str).to_numpy().ravel())|set(controls))
    matrices=[];lower=[];upper=[]
    special=next((s for s in slots if s in ('Captain','MVP')),None)
    for name in names:
        cfg=controls.get(name,{})
        def pct(key,default):
            value=pd.to_numeric(cfg.get(key,default),errors='coerce')
            return float(np.clip(value if pd.notna(value) else default,0,100))
        overall=frame[slots].astype(str).eq(name).any(axis=1).to_numpy(int)
        matrices.append(overall)
        lower.append(math.ceil(count*(100 if cfg.get('Lock',False) else pct('Min Exposure %',0))/100-1e-9))
        upper.append(math.floor(count*(0 if cfg.get('Fade',False) else pct('Max Exposure %',100))/100+1e-9))
        if special:
            role=frame[special].astype(str).eq(name).to_numpy(int)
            matrices.extend([role,overall-role])
            lower.extend([math.ceil(count*pct(special+' Min %',0)/100-1e-9),0])
            upper.extend([math.floor(count*pct(special+' Max %',100)/100+1e-9),math.floor(count*pct('Flex Max %',100)/100+1e-9)])
    return np.column_stack(matrices),np.array(lower),np.array(upper)


def prepare(frame,slots):
    special=next((s for s in slots if s in ('Captain','MVP')),None)
    ranked=frame.sort_values('_top1',ascending=False,kind='stable').copy()
    if ranked[slots].isna().any().any():raise ValueError('Missing roster identity')
    if ranked[slots].astype(str).apply(lambda row:len(set(row))!=len(slots),axis=1).any():raise ValueError('Duplicate player within frozen roster')
    def key(row):return ((str(row[special]),) if special else ())+tuple(sorted(str(row[s]) for s in slots if s!=special))
    return ranked.loc[~ranked.apply(key,axis=1).duplicated()].reset_index(drop=True)


def portfolios(frame,slots,count,controls,diversity,trials=1000,seed=20261103):
    """All selection runs before compare() opens standings; fixed full pool."""
    if not 1<=trials<=10000:raise ValueError('Trials must be between 1 and 10000')
    frame=prepare(frame,slots)
    if len(frame)<count:raise ValueError('Insufficient unique frozen candidates')
    matrix,lower,upper=constraints(frame,slots,count,controls)
    def valid(indices):
        totals=matrix[indices].sum(axis=0)
        return bool(np.all(totals>=lower)&np.all(totals<=upper))
    output={}
    # Automatic diversity caps remain soft preferences for the shared selector;
    # all methods share manual hard constraints, never quietly make soft hard.
    for label,value in [('deterministic',diversity)]+[('diversity_'+str(x),x) for x in (0,25,50,75,100)]:
        try:
            selected=select_portfolio(frame,slots,count,'_top1',controls=controls,diversity=value)
            check,lo,hi=constraints(selected,slots,count,controls)
            totals=check.sum(axis=0)
            if not ((totals>=lo).all() and (totals<=hi).all()):raise ValueError('Returned portfolio violates fixed constraints')
            output[label]={'portfolio':selected,'effective_automatic_cap':selected.attrs.get('effective_auto_cap_pct')}
        except ValueError as error:output[label]={'error':str(error)}
    # Normalized raw overlap = |intersection| / roster size; equal-sized rosters
    # make Jaccard a monotonic transformation, hence identical distance ordering.
    roster_names=np.unique(frame[slots].astype(str).to_numpy());lookup={n:i for i,n in enumerate(roster_names)}
    roster=np.zeros((len(frame),len(lookup)),np.int8)
    for i,row in enumerate(frame[slots].astype(str).to_numpy()):roster[i,[lookup[n] for n in row]]=1
    chosen=[];used=np.zeros(len(frame),bool);totals=np.zeros(matrix.shape[1],int);overlap=np.zeros(len(frame))
    for step in range(count):
        remaining=count-step-1
        allowed=(~used)&np.all(totals+matrix<=upper,axis=1)&np.all(totals+matrix+remaining>=lower,axis=1)
        options=np.flatnonzero(allowed)
        if not len(options):break
        best=int(options[np.argmin(overlap[options])]);chosen.append(best);used[best]=True;totals+=matrix[best]
        overlap=np.maximum(overlap,(roster@roster[best])/len(slots))
    output['distance']={'portfolio':frame.iloc[chosen]} if len(chosen)==count and valid(chosen) else {'error':'Bounded greedy distance search found no full valid portfolio; no constraints relaxed'}
    rng=np.random.default_rng(seed);accepted=[];attempts=0
    while len(accepted)<trials and attempts<trials*100:
        indices=rng.choice(len(frame),count,replace=False);attempts+=1
        if valid(indices):accepted.append(indices)
    # Do not substitute biased constructive samples for uniform rejection draws.
    if len(accepted)!=trials:output['random']={'error':f'Only {len(accepted)}/{trials} accepted within {attempts} draws; random benchmark unavailable'}
    else:
        for i,indices in enumerate(accepted):output['random_'+str(i)]={'portfolio':frame.iloc[indices]}
    # A distinct bounded swap-chain benchmark works when rejection acceptance is
    # tiny. Never call these uniform or independent draws; mixing is unproven.
    baseline=output.get('deterministic',{}).get('portfolio')
    transitions=0
    if baseline is not None:
        lookup_rows={tuple(row):i for i,row in enumerate(frame[slots].astype(str).to_numpy())}
        chosen=np.array([lookup_rows[tuple(row)] for row in baseline[slots].astype(str).to_numpy()])
        totals=matrix[chosen].sum(axis=0);used=set(chosen.tolist())
        swap_rng=np.random.default_rng(seed+1)
        burn_in=100*count;spacing=count
        for step in range(burn_in+trials*spacing):
            position=int(swap_rng.integers(count));incoming=int(swap_rng.integers(len(frame)))
            outgoing=int(chosen[position])
            if incoming not in used:
                proposed=totals-matrix[outgoing]+matrix[incoming]
                if np.all(proposed>=lower) and np.all(proposed<=upper):
                    chosen[position]=incoming;used.remove(outgoing);used.add(incoming);totals=proposed;transitions+=1
            if step>=burn_in and (step-burn_in+1)%spacing==0:
                output['swap_random_'+str((step-burn_in)//spacing)]={'portfolio':frame.iloc[chosen.copy()]}
    else:output['swap_random']={'error':'No valid deterministic seed portfolio; swap benchmark unavailable'}
    return output,{'trials_requested':trials,'accepted':len(accepted),'attempts':attempts,'seed':seed,'unique_candidates':len(frame),
                   'swap_seed':seed+1,'swap_accepted_transitions':transitions,'swap_burn_in_proposals':100*count,'swap_proposals_between_samples':count,
                   'swap_scope':'Dependent random-swap samples from deterministic seed; uniformity and convergence not established'}


def replay(build,standings,slate_group,trials=1000,seed=20261103):
    if not slate_group.strip():raise ValueError('Explicit shared slate group required')
    metadata={}
    def factory(*args):
        selected,info=portfolios(*args,trials=trials,seed=seed);metadata.update(info);return selected
    report=compare(build,standings,selection_factory=factory)
    report['constraint_scope']=report['constraint_scope'].replace('identical current selector for every method.','hard limits shared across selector, distance and random methods.')
    report['limitations']=[line.replace('Current shared selector is used for all challengers; this is not an exact replay of older selector implementations.','Deterministic/diversity methods use the current shared selector; distance/random use separate fixed algorithms with the same hard limits. Older selector implementations are not reproduced.') for line in report['limitations']]
    methods=report['methods'];baseline=methods.get('deterministic',{}).get('estimated_net')
    for item in methods.values():
        net=item.get('estimated_net');item['paired_net_delta']=None if baseline is None or net is None else net-baseline
    random=[item for name,item in methods.items() if name.startswith('random_')]
    complete=bool(random) and all(item.get('estimated_net') is not None for item in random)
    summary={'status':'complete' if complete else 'unavailable or incomplete actuals','evaluated_trials':len(random),'fully_scored_trials':sum(item.get('estimated_net') is not None for item in random)}
    if complete:
        nets=np.array([item['estimated_net'] for item in random]);deltas=nets-baseline if baseline is not None else None
        summary.update(mean_net=float(nets.mean()),median_net=float(np.median(nets)),loss_frequency=float((nets<0).mean()),
                       mean_paired_net_delta=None if deltas is None else float(deltas.mean()),median_paired_net_delta=None if deltas is None else float(np.median(deltas)))
    swaps=[item for name,item in methods.items() if name.startswith('swap_random_')]
    swap_complete=bool(swaps) and all(item.get('estimated_net') is not None for item in swaps)
    swap_summary={'status':'complete' if swap_complete else 'unavailable or incomplete actuals','evaluated_trials':len(swaps),'fully_scored_trials':sum(item.get('estimated_net') is not None for item in swaps)}
    if swap_complete:
        nets=np.array([item['estimated_net'] for item in swaps])
        swap_summary.update(mean_net=float(nets.mean()),median_net=float(np.median(nets)),loss_frequency=float((nets<0).mean()),
                            mean_paired_net_delta=None if baseline is None else float((nets-baseline).mean()))
    report['methods']={name:item for name,item in methods.items() if not name.startswith(('random_','swap_random_'))}
    report.update(protocol_version=PROTOCOL_VERSION,slate_group=slate_group,random_sampling=metadata,random_summary=summary,
                  random_trials=random,swap_random_summary=swap_summary,swap_random_trials=swaps,independent_unit='slate_group; cross-platform contests in the same group are dependent',
                  candidate_filter='Entire frozen unique candidate pool; no outcome-based or top-250 cutoff',
                  constraint_comparison='Identical manual hard constraints; automatic diversity preferences differ by method',
                  outcome_blind_selection=True)
    return report



def update_ledger(path,report):
    """Idempotent contest records nested by dependent slate group, no pooling."""
    path=Path(path)
    ledger=json.loads(path.read_text()) if path.exists() else {'schema':1,'groups':{}}
    if ledger.get('schema')!=1:raise ValueError('Unsupported ledger schema')
    key=report['format']+':'+report['contest_id']
    if any(key in contests for group_name,contests in ledger['groups'].items() if group_name!=report['slate_group']):
        raise ValueError('Contest already assigned to another dependent slate group')
    group=ledger['groups'].setdefault(report['slate_group'],{})
    group[key]={key:report[key] for key in ('format','contest_id','build_sha256','standings_sha256','protocol_version','methods','random_summary','random_sampling','swap_random_summary')}
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(ledger,indent=2,allow_nan=False)+'\n');temporary.replace(path)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('build','standings','slate-group','output'):p.add_argument('--'+key,required=True)
    p.add_argument('--ledger');p.add_argument('--trials',type=int,default=1000);p.add_argument('--seed',type=int,default=20261103)
    a=p.parse_args();report=replay(a.build,a.standings,a.slate_group,a.trials,a.seed)
    path=Path(a.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    if a.ledger:update_ledger(a.ledger,report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('random_trials','swap_random_trials','metric_signal_diagnostics')},indent=2))

if __name__=='__main__':main()
