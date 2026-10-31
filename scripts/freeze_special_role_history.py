"""Freeze rank-based Captain/MVP priors from completed contest standings, offline."""
import argparse,hashlib,json,sys,zipfile
from pathlib import Path
from collections import Counter
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_contest_history import parse_lineups,verified_fanduel_mvp_first,name_key

def freeze(path,site,available_date):
    path=Path(path)
    if path.suffix=='.zip':
        with zipfile.ZipFile(path) as z:
            members=[n for n in z.namelist() if n.endswith('.csv')]
            if len(members)!=1:raise ValueError('One standings CSV required')
            frame=pd.read_csv(z.open(members[0]),low_memory=False)
    else:frame=pd.read_csv(path,low_memory=False)
    lineups=parse_lineups(frame)
    if not lineups or any(len(r)!=6 for r in lineups):raise ValueError('Complete six-player lineups required')
    if site=='fd':lineups=verified_fanduel_mvp_first(frame,lineups)
    total=Counter(name_key(n) for row in lineups for _,n in row)
    special=Counter()
    for row in lineups:
        roles=[name_key(n) for slot,n in row if slot in {'CPT','MVP'}]
        if len(roles)!=1:raise ValueError('Exactly one verified special role required')
        special.update(roles)
    ordered=sorted(total,key=lambda n:(-total[n],n))
    # Ties in overall ownership share their combined special-role mass equally.
    masses=[]
    for name in ordered:
        tied=[n for n in ordered if total[n]==total[name]]
        masses.append(sum(special[n] for n in tied)/len(tied)/len(lineups))
    return dict(site=site,available_date=available_date,source_file=path.name,
        source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),entries=len(lineups),
        rank_basis='all-slot entry ownership descending',special_mass_by_rank=masses)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dk',required=True);p.add_argument('--fd',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    result={'schema_version':'1.0','offline_only':True,'profiles':[
        freeze(a.dk,'dk','2026-10-16'),freeze(a.fd,'fd','2026-10-20')],
        'limitations':['One contest per site; exploratory prior, not validated on multiple slates.',
        'Current projected all-slot ownership rank is a proxy for historical actual ownership rank.',
        'No historical player identities or postgame scores are used as current-slate predictors.']}
    Path(a.output).write_text(json.dumps(result,indent=2)+'\n')
