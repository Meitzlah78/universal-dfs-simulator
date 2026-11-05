"""Retain exact swap-selection evidence without requiring an export click."""
import io,json,zipfile,re
from datetime import datetime,timezone
from hashlib import sha256
import pandas as pd
from simmah_nba_rules import rules_for


def make_swap_package(pool,contest_id,result):
    from simmah_slate_workspaces import encode
    stamp=datetime.now(timezone.utc);rules=rules_for(pool)
    rows=pd.DataFrame(result['candidate_player_ids'],columns=rules['slots'])
    if len(rows)!=len(result['candidate_report']):raise ValueError('Swap archive candidate scores are misaligned')
    files={'late_swap.json':json.dumps(encode(result),allow_nan=False).encode(),
        'candidate_lineups.csv':rows.to_csv(index=False).encode('utf-8-sig'),
        'candidate_scores.csv':result['candidate_report'].to_csv(index=False).encode('utf-8-sig'),
        'portfolio.csv':pd.DataFrame(result['lineups'],columns=rules['slots']).to_csv(index=False).encode('utf-8-sig'),
        'player_pool.csv':pool.to_csv(index=False).encode('utf-8-sig')}
    from pathlib import Path
    for name in ('simmah_nba_swap_portfolio.py','simmah_nba_sim_late_swap.py','simmah_nba_late_swap.py'):
        files['implementation/'+name]=(Path(__file__).parent/name).read_bytes()
    manifest={'schema':1,'kind':'nba_late_swap_selection','sport':'NBA','platform':rules['platform'],
        'contest_id':str(contest_id),'captured_at_utc':stamp.isoformat(),
        'scope':'Exact selection evidence; export may reconcile later tipoffs. Not proof of site submission.',
        'files':{name:{'sha256':sha256(raw).hexdigest(),'bytes':len(raw)} for name,raw in files.items()}}
    files['manifest.json']=json.dumps(manifest,indent=2).encode()
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for name,raw in files.items():z.writestr(name,raw)
    cid=re.sub(r'[^A-Za-z0-9_-]','_',str(contest_id))
    return f'Simmah_NBA_{rules["platform"]}_{cid}_{stamp.strftime("%Y%m%dT%H%M%SZ")}_Late_Swap_Audit.zip',buf.getvalue(),manifest


def retain_swap_run(st,pool,contest_id,result):
    from simmah_nba_diagnostics import retain_package,package_reference
    package=make_swap_package(pool,contest_id,result)
    retain_package(st,package)
    st.session_state['nba_late_swap_audit_reference']={'contest_id':str(contest_id),**package_reference(package)}


def render_swap_archive(st,contest_id):
    from simmah_nba_diagnostics import package_bytes
    from simmah_slate_workspaces import workspace_download_button
    reference=st.session_state.get('nba_late_swap_audit_reference')
    if not reference or reference['contest_id']!=str(contest_id):return
    raw=package_bytes(st,reference)
    if raw is not None:
        workspace_download_button(st,'DOWNLOAD LATE SWAP AUDIT',raw,reference['filename'],
            'application/zip',key='nba_late_swap_audit_download_'+str(contest_id),on_click='ignore')
