"""Parse DD's copied NBA table without inventing exact censored ownership."""
import re
import hashlib
import io
import pandas as pd
from simmah_nba_draftdashboard_fields import apply_fields
from simmah_nba_projections import player_key


def parse_text(text, platform):
    opposite={'DraftKings':'FD','FanDuel':'DK'}[platform]
    labels=set(re.findall(r'(?m)^[+-]\$[\d,]+ (DK|FD)\s*$',text))
    if labels!={opposite}:
        raise ValueError('DD text site cannot be verified from salary-comparison labels')
    lines=[s.strip() for s in text.splitlines() if s.strip()]
    starts=[i for i in range(len(lines)-3)
        if all(re.fullmatch(r'\d+',lines[i+j]) for j in range(3))
        and re.search('[A-Za-z]',lines[i+3])]
    records=[]
    def number(s):return float(s.strip().rstrip('%x').replace(',',''))
    for k,start in enumerate(starts):
        b=lines[start:starts[k+1] if k+1<len(starts) else len(lines)]
        try:
            match=next(i for i,s in enumerate(b) if re.fullmatch(r'[A-Z]{2,3} vs [A-Z]{2,3}',s))
            team,opp=b[match].split(' vs ')
            total,salary=b[match+1].split('\t')
            def before(label):return b[b.index(label)-1].split('\t')[-1].strip()
            own_index=next(i for i,s in enumerate(b) if s.startswith('Own\t'))
            own=b[own_index-1].split('\t')[-1].strip()
            records.append({'Player':b[3],'Team':team,'Opponent':opp,'Position':b[match-2],
                'Salary':number(salary.replace('$','')),
                'PRO':number(b[own_index].split('\t')[-1]),
                'MIN':number(before('Last 3 Mins:')),'USE':number(before('Last 3 Usage:')),
                'FPPG':number(before('Last 3 Games:')),
                'VS OPP':number(b[b.index('Last 3 '+opp+':')-1].split('\t')[-1]),
                'DraftDashboard Displayed OWN':own,
                'DashRank':int(b[0]),'Opponent Rank':int(b[1]),'Position Rank':int(b[2]),
                'Game Total':number(total),'VAL':number(b[b.index('Proj')+1]),
                'PPM':number(next(s for s in b if s.startswith('Value\t')).split('\t')[-1]),
                'HIT':number(next(s for s in b if s.startswith('FPPM\t')).split('\t')[-1]),
                'DraftDashboard Last 3 Games':b[b.index('Last 3 Games:')+1].split('\t')[0].strip(),
                'DraftDashboard Last 3 Minutes':b[b.index('Last 3 Mins:')+1].split('\t')[0].strip(),
                'DraftDashboard Last 3 Usage':b[b.index('Last 3 Usage:')+1].split('\t')[0].strip()})
        except (ValueError,IndexError,StopIteration) as exc:
            raise ValueError('Incomplete DD player block: '+b[3]) from exc
    if not records:raise ValueError('No complete DD player rows found')
    frame=pd.DataFrame(records)
    keys=[player_key(r.Player,r.Team) for r in frame.itertuples()]
    if len(set(keys))!=len(keys):raise ValueError('Duplicate DD player/team rows')
    # Validate every typed attribute, including unmatched rows, before applying.
    apply_fields(pd.DataFrame(index=range(len(frame))),frame,keys,keys)
    return frame


def apply_text(pool, text, platform, day, *, confirmed=False,file_format='txt'):
    if not confirmed:raise ValueError('Confirm this undated DD text belongs to the selected slate date')
    from simmah_nba_rules import rules_for
    if rules_for(pool)['platform']!=platform:raise ValueError('DD site differs from salary slate')
    if pool.attrs.get('slate_date') and str(pool.attrs['slate_date'])!=str(day):raise ValueError('DD date differs from salary slate')
    if file_format=='txt':frame=parse_text(text,platform)
    elif file_format=='csv':
        frame=pd.read_csv(io.StringIO(text),keep_default_na=False)
        required={'Player','Team','Opponent','Salary','PRO','MIN','Site','Sport','Source','Slate Date'}
        if frame.empty or not required<=set(frame):raise ValueError('Choose the DD player-attributes CSV, not an entries file')
        if set(frame['Site'])!={platform} or set(frame['Sport'])!={'NBA'} or set(frame['Source'])!={'DraftDashboard'}:
            raise ValueError('DD attributes belong to a different site, sport or source')
        if set(frame['Slate Date'].astype(str))!={str(day)}:raise ValueError('DD CSV date differs from current slate')
        frame['Salary']=pd.to_numeric(frame['Salary'],errors='raise')
    else:raise ValueError('Unsupported DD attributes format')
    keys=[player_key(r.Player,r.Team) for r in frame.itertuples()]
    if len(set(keys))!=len(keys):raise ValueError('Duplicate DD player/team rows')
    pool_keys=[player_key(r.Name,r.Team) for r in pool.itertuples()]
    if len(set(pool_keys))!=len(pool_keys):raise ValueError('Ambiguous salary-slate player/team rows')
    source=dict(zip(keys,frame.to_dict('records')))
    from simmah_nba_ownership import active_players
    missing=[str(pool.iloc[i]['Name']) for i,key in enumerate(pool_keys)
        if key not in source and active_players(pool)[i]]
    if missing:raise ValueError('DD text missing eligible players: '+', '.join(missing))
    for i,key in enumerate(pool_keys):
        if key not in source:continue
        row=source[key];p=pool.iloc[i]
        if float(p['Salary'])!=row['Salary'] or player_key('',p['Opponent'])[1]!=player_key('',row['Opponent'])[1]:
            raise ValueError('DD salary/opponent differs from current slate: '+str(p['Name']))
    result,fields=apply_fields(pool,frame,keys,pool_keys)
    for col in frame:
        if col.startswith('DraftDashboard '):
            values=dict(zip(keys,frame[col]));result[col]=[values.get(key) for key in pool_keys]
    result.attrs['draftdashboard_text']={'sha256':hashlib.sha256(text.encode()).hexdigest(),
        'site':platform,'date':str(day),'date_confirmation':'user confirmed current selected slate',
        'rows':len(frame),'matched':sum(key in source for key in pool_keys),
        'ownership_applied':False,'fields':fields}
    return result


def render_text_upload(st,pool,platform,day):
    from simmah_slate_workspaces import workspace_file_uploader
    st.caption('DD player attributes: projections, projected MIN, usage and ranks. Displayed OWN stays reference-only; field ownership keeps its separately validated source.')
    upload=workspace_file_uploader(st,'DraftDashboard player attributes (.csv or .txt)',type=['csv','txt'],key='nba_dd_text_'+platform)
    if upload is None:return pool
    data=upload.getvalue();digest=hashlib.sha256(data).hexdigest()[:12]
    if not st.checkbox(f'This DD player table is for {platform}, {day}',key='nba_dd_confirm_'+platform+'_'+str(day)+'_'+digest):return pool
    try:result=apply_text(pool,data.decode('utf-8-sig'),platform,day,confirmed=True,file_format='csv' if upload.name.lower().endswith('.csv') else 'txt')
    except (ValueError,UnicodeError) as exc:
        st.error('DraftDashboard attributes not applied: '+str(exc));st.stop();return pool
    st.success(f"DD attributes loaded: {result.attrs['draftdashboard_text']['matched']} matched players · {platform} · {day}")
    return result
