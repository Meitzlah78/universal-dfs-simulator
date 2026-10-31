from simmah_slate_workspaces import workspace_button, workspace_download_button, workspace_file_uploader
"""Reusable contest metadata only; never persist entry IDs or opponent rosters."""
import json
import math
import os
import tempfile
from pathlib import Path

FORMATS={'DraftKings Classic','DraftKings Showdown','FanDuel Full Roster','FanDuel Single Game'}


def record(contest,format_name):
    if format_name not in FORMATS or not str(contest.get('id') or '').strip():
        raise ValueError('A supported format and exact contest ID are required')
    out={'format':format_name,'id':str(contest['id']).strip(),'name':str(contest.get('name') or contest['id'])}
    for key in ['field_size','entry_fee','max_entries_per_user','prize_pool']:
        value=contest.get(key)
        if value is not None:
            number=float(value)
            if not math.isfinite(number) or number<0:raise ValueError('Invalid contest '+key)
            if key in {'field_size','max_entries_per_user'}:
                if number!=int(number) or number<1:raise ValueError('Invalid contest '+key)
                number=int(number)
            out[key]=number
    tiers=contest.get('payouts') or contest.get('payout_tiers')
    if tiers is not None:
        rows=[];last=0
        for first,end,prize in tiers:
            if int(first)!=first or int(end)!=end or first<=last or end<first or not math.isfinite(float(prize)) or prize<0:
                raise ValueError('Invalid or overlapping payout tiers')
            rows.append([int(first),int(end),float(prize)]);last=end
        if rows and out.get('field_size',last)<last:raise ValueError('Payout exceeds contest capacity')
        out['payouts']=rows
    return out


def merge(*catalogs):
    rows={}
    for catalog in catalogs:
        for item in catalog.get('contests',[]):
            clean=record(item,item['format']);key=(clean['format'],clean['id'])
            rows[key]={**rows.get(key,{}),**clean}
    return {'schema':1,'contests':list(rows.values())}


def load(path):
    path=Path(path)
    return merge(json.loads(path.read_text())) if path.exists() else {'schema':1,'contests':[]}


def save(path,catalog):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    clean=merge(catalog)
    descriptor,temp=tempfile.mkstemp(prefix='contest-',suffix='.json',dir=path.parent)
    try:
        with os.fdopen(descriptor,'w') as stream:json.dump(clean,stream,indent=2)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    return clean


def restore(active,saved,format_name):
    clean=record(saved,saved['format'])
    if clean['format']!=format_name or clean['id']!=str(active.get('id','')):
        raise ValueError('Upload the entry file for this exact contest and format first')
    result=dict(active)
    for key in ['field_size','entry_fee','max_entries_per_user','prize_pool','payouts']:
        if key in clean:result[key]=clean[key]
    return result


def render_panel(st,active,format_name):
    """Use reusable payscales for every single-game slate."""
    if format_name in {"DraftKings Showdown", "FanDuel Single Game"}:
        from simmah_payscales import render_panel as render_payscales
        return render_payscales(st, dict(active), format_name)
    root=Path(__file__).resolve().parent/'data'
    local=root/'saved_contests_local.json'
    try:
        catalog=merge(load(root/'saved_contests_seed.json'),load(local))
    except (OSError,ValueError,TypeError,KeyError):
        catalog=load(root/'saved_contests_seed.json')
        st.warning('Saved contest metadata could not load; using built-in contests.')
    # Capture a previously confirmed payout ladder only for this exact contest.
    active=dict(active)
    cid=str(active.get('id',''))
    if cid and str(st.session_state.get('contest_payout_contest_id',''))==cid and format_name=='DraftKings Showdown':
        schedule=st.session_state.get('contest_payout_schedule')
        if schedule is not None:
            tiers=[]
            for rank,value in enumerate(schedule,1):
                value=float(value)
                if value<=0:continue
                if tiers and tiers[-1][1]==rank-1 and tiers[-1][2]==value:tiers[-1][1]=rank
                else:tiers.append([rank,rank,value])
            if tiers:active['payouts']=tiers
    session=st.session_state.get('saved_contest_catalog',{'schema':1,'contests':[]})
    catalog=merge(catalog,session)
    compatible=[r for r in catalog['contests'] if r['format']==format_name]
    key='saved_contest_choice_'+format_name
    from simmah_payscales import render_panel as render_payscales
    active = render_payscales(st, active, format_name)
    st.write('### Exact contest backups (optional)')
    st.caption('To reuse a payout table on any slate, select Saved payscales above. This backup section restores details for the original contest only.')
    if compatible:
        choices={r['id']:r for r in compatible}
        selected=st.selectbox('Previously saved contest',list(choices),
            format_func=lambda cid:choices[cid]['name']+' | ID '+cid,key=key)
        chosen=choices[selected]
        st.caption(f"Saved field: {chosen.get('field_size','unknown')} · Fee: {chosen.get('entry_fee','unknown')} · Payout tiers: {len(chosen.get('payouts',[]))}")
        if workspace_button(st,'Restore exact contest backup',key=key+'_use'):
            if str(active.get('id',''))!=chosen['id']:
                st.info('This backup belongs to another contest. Select its payout table under Saved payscales above to use that ladder on your current slate.')
            else:
                st.session_state[key+'_active']=chosen
        pending=st.session_state.get(key+'_active')
        if pending and pending.get('id')==str(active.get('id','')):
            active=restore(active,pending,format_name)
            if format_name=='DraftKings Showdown' and active.get('payouts') and active.get('field_size'):
                from simmah_contests import payout_vector
                st.session_state['contest_payout_schedule']=payout_vector(active['field_size'],active['payouts'])
                st.session_state['contest_payout_contest_id']=str(active['id'])
                st.session_state['contest_payout_source_name']='Saved exact-contest payout table'
            st.success('Saved contest details selected for the matching entry file.')
    else:
        st.caption('No saved contests for this format yet. Select a contest from your entry file, then save its details.')
    if active.get('id') and workspace_button(st,'Save selected contest details',key=key+'_save'):
        try:
            catalog=merge(catalog,{'contests':[record(active,format_name)]})
            save(local,catalog);st.session_state['saved_contest_catalog']=catalog
            st.success('Contest details saved. Export a backup to keep them across hosting redeploys.')
            st.rerun()
        except (OSError,ValueError,TypeError) as error:
            st.error('Could not save contest details: '+str(error))
    with st.expander('Contest backup / restore',expanded=False):
        workspace_download_button(st,'Download saved contests',json.dumps(catalog,indent=2),'Simmah_Saved_Contests.json','application/json',key=key+'_backup')
        uploaded=workspace_file_uploader(st,'Restore saved contests JSON',type=['json'],key=key+'_restore')
        if uploaded is not None and workspace_button(st,'Restore saved contest details',key=key+'_restore_button'):
            try:
                catalog=merge(catalog,json.loads(uploaded.getvalue()))
                save(local,catalog);st.session_state['saved_contest_catalog']=catalog;st.rerun()
            except (OSError,ValueError,TypeError,KeyError):st.error('Invalid saved-contest backup.')
    return active
