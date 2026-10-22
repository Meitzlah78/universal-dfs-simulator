"""Reusable, explicitly selected NFL payout ladders; no lineup generation changes."""
import json
import math
import re
from pathlib import Path
from simmah_slate_workspaces import workspace_button, workspace_download_button, workspace_file_uploader


def validate_tiers(tiers):
    result=[]; last=0; previous=float('inf')
    for first,end,prize in tiers:
        first_n,end_n=float(first),float(end); prize=float(prize)
        if not all(math.isfinite(v) for v in (first_n,end_n,prize)) or first_n!=int(first_n) or end_n!=int(end_n):
            raise ValueError('Ranks must be whole numbers and prizes must be finite.')
        first,end=int(first_n),int(end_n)
        if first!=last+1 or end<first or prize<0 or prize>previous:
            raise ValueError('Tiers must cover consecutive ranks from 1, without overlaps, and prizes must not increase.')
        result.append([first,end,prize]);last=end;previous=prize
    if not result or not any(row[2]>0 for row in result):raise ValueError('Enter at least one paid tier.')
    return result


def parse_tiers(text):
    rows=[]
    for line in text.splitlines():
        line=line.strip().strip('|').strip()
        if not line:continue
        match=re.fullmatch(r'(\d+)(?:st|nd|rd|th)?\s*(?:[-–—]\s*(\d+)(?:st|nd|rd|th)?)?\s*(?:\||,|\t|:)\s*\$?([\d,]+(?:\.\d+)?)',line,re.I)
        if not match:raise ValueError('Use one tier per line: 1,250 or 7-8,30 (no headings).')
        rows.append([int(match[1]),int(match[2] or match[1]),float(match[3].replace(',',''))])
    return validate_tiers(rows)


def catalog(root):
    rows={}
    legacy=root/'dk_payout_library.json'
    if legacy.exists():
        for profile in json.loads(legacy.read_text()).get('profiles',[]):
            name=profile.get('contest_family') or profile['contest_name']
            rows['dk:'+name]={'name':name,'site':'DraftKings','payouts':validate_tiers(profile['payout_ranges'])}
    seed=root/'saved_contests_seed.json'
    if seed.exists():
        for profile in json.loads(seed.read_text()).get('contests',[]):
            if profile.get('payouts'):
                site='DraftKings' if profile['format'].startswith('DraftKings') else 'FanDuel'
                rows[site+':'+profile['name']]={'name':profile['name'],'site':site,'payouts':validate_tiers(profile['payouts'])}
    path=root/'saved_payscales.json'
    if path.exists():rows.update(json.loads(path.read_text()).get('profiles',{}))
    return rows


def render_panel(st,active,format_name):
    root=Path(__file__).resolve().parent/'data';path=root/'saved_payscales.json'
    site='DraftKings' if format_name.startswith('DraftKings') else 'FanDuel'
    key='payscale_'+format_name
    active=dict(active)
    try:profiles=catalog(root)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        st.error('Saved payscales could not load: '+str(exc));return active
    profiles.update(st.session_state.get('saved_payscales',{}))
    choices={pid:p for pid,p in profiles.items() if p['site']==site}
    st.write('### Saved payscales')
    choice=st.selectbox('Payscale', ['']+list(choices),format_func=lambda pid:choices[pid]['name'] if pid else 'Use current contest payouts',key=key+'_choice')
    base_key=key+'_base_'+str(active.get('id',''))
    if not active.get('payout_profile_id'):
        st.session_state[base_key]=dict(active)
    elif not choice:
        active=dict(st.session_state.get(base_key,active))
        if format_name=='DraftKings Showdown':
            st.session_state.pop('contest_payout_schedule',None)
            st.session_state.pop('contest_payout_contest_id',None)
    if choice:
        try:
            tiers=validate_tiers(choices[choice]['payouts'])
            capacity=int(active.get('field_size') or 0)
            if not capacity:
                capacity=st.number_input('Exact contest field size for payscale',min_value=2,value=None,step=1,key=key+'_capacity')
                if capacity is not None:active['field_size']=int(capacity)
            st.caption(f'{tiers[-1][1]:,} paid places · ${sum((b-a+1)*p for a,b,p in tiers):,.2f} total prizes')
            if capacity is None or capacity<tiers[-1][1]:
                st.warning('Enter a contest field size at least as large as the last paid rank before using this payscale.')
            else:
                active.update(payouts=tiers,payout_profile_id=choice,prize_pool=sum((b-a+1)*p for a,b,p in tiers))
                if format_name=='DraftKings Showdown' and active.get('id'):
                    from simmah_contests import payout_vector
                    st.session_state['contest_payout_schedule']=payout_vector(capacity,tiers)
                    st.session_state['contest_payout_contest_id']=str(active['id'])
                    st.session_state['contest_payout_source_name']='Selected saved payscale: '+choices[choice]['name']
                st.caption('Selected for this contest. Re-run Contest Sim to update payout results.')
        except (ValueError,TypeError) as exc:st.error(str(exc))
    with st.expander('Save a payscale',expanded=False):
        name=st.text_input('Payscale name',key=key+'_name')
        text=st.text_area('Payout tiers — one rank or range per line',key=key+'_tiers',help='Example: 1,250 followed by 2,150 and 3-5,100. No headings.')
        if workspace_button(st,'Save payscale',key=key+'_save'):
            try:
                if not name.strip():raise ValueError('Name this payscale first.')
                tiers=parse_tiers(text) if text.strip() else validate_tiers(active.get('payouts') or active.get('payout_tiers') or [])
                pid=site+':'+name.strip()
                if pid in profiles:raise ValueError('That name already exists. Use a new name to preserve the saved scale.')
                profiles[pid]={'name':name.strip(),'site':site,'payouts':tiers}
                persist(path,profiles)
                st.session_state['saved_payscales']=profiles
                st.success('Payscale saved. Select it above; download a backup to keep it across hosting rebuilds.')
            except (ValueError,OSError,TypeError) as exc:st.error('Could not save payscale: '+str(exc))
        upload=workspace_file_uploader(st,'Restore payscales backup',type=['json'],key=key+'_restore')
        if upload is not None and workspace_button(st,'Restore payscales',key=key+'_restore_use'):
            try:
                incoming=json.loads(upload.getvalue())['profiles']
                for pid,profile in incoming.items():
                    if profile['site'] not in {'DraftKings','FanDuel'} or not profile['name'].strip():raise ValueError('Invalid payscale metadata')
                    profile['payouts']=validate_tiers(profile['payouts'])
                profiles.update(incoming)
                persist(path,profiles)
                st.session_state['saved_payscales']=profiles
                st.rerun()
            except (ValueError,KeyError,TypeError,OSError) as exc:st.error('Could not restore payscales: '+str(exc))
        workspace_download_button(st,'Download payscales backup' ,json.dumps({'version':1,'profiles':profiles},indent=2),'Simmah_Payscales.json','application/json',key=key+'_backup')
    return active


def persist(path,profiles):
    import os,tempfile
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(dir=path.parent,prefix='payscales-',suffix='.json')
    try:
        with os.fdopen(fd,'w') as stream:json.dump({'version':1,'profiles':profiles},stream,indent=2)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def reapply_showdown(st,active):
    """Explicit selection takes priority over later automatic payout fetches."""
    choice=st.session_state.get('payscale_DraftKings Showdown_choice')
    if choice and active.get('payout_profile_id')==choice and active.get('payouts'):
        from simmah_contests import payout_vector
        st.session_state['contest_payout_schedule']=payout_vector(int(active['field_size']),active['payouts'])
        st.session_state['contest_payout_contest_id']=str(active['id'])
        st.session_state['contest_payout_source_name']='Selected saved payscale: '+choice
