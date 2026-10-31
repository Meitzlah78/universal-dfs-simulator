"""Anonymous completed-contest profiles and inspectable field calibration.

Only aggregate feature histograms and file digests are persisted. Player names,
usernames, entry IDs and actual fantasy scores are not part of the model store.
"""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import io
import json
import os
import re
import tempfile
import zipfile
import numpy as np
import pandas as pd

SCHEMA = 1
SLOTS = {'QB','RB','WR','TE','K','FLEX','DST','D','DEF','CPT','CAPTAIN','MVP','UTIL','ANYFLEX'}
TOKEN = re.compile(r'\b(CAPTAIN|ANYFLEX|FLEX|CPT|MVP|QB|RB|WR|TE|K|DST|DEF|UTIL|D)\s*:?[ ]+(.+?)(?=\s+(?:CAPTAIN|ANYFLEX|FLEX|CPT|MVP|QB|RB|WR|TE|K|DST|DEF|UTIL|D)\s*:?[ ]+|$)')
BINS = {
    'ownership_sum': np.arange(0, 951, 10),
    'captain_popularity': np.arange(0, 102, 2),
    'ownership_product_log': np.arange(-100, 2, 2),
    'salary_left': np.r_[-1, np.arange(0, 10001, 250), 100000],
    'qb_pass_catcher_stack_count': np.arange(-.5, 8.5),
    'bring_back_count': np.arange(-.5, 8.5),
    'rb_dst_stack': np.array([-.5,.5,1.5]),
}


def name_key(value):
    name = re.sub(r'\s+\(\d+(?:-\d+)?\)[,; ]*$','',str(value or '').casefold().strip())
    name = re.sub(r'\s+(jr|sr|ii|iii|iv|v)\.?$','',name)
    return re.sub('[^a-z0-9]','',name)


def stake_bucket(fee):
    if fee is None: return 'UNKNOWN'
    fee = float(fee)
    return 'LOW' if fee <= 4 else 'FLAGSHIP' if fee <= 30 else 'MEDIUM' if fee < 100 else 'HIGH'


def format_key(platform, mode):
    site = str(platform).casefold()
    mode = str(mode).casefold()
    single = any(x in mode for x in ('showdown','single','cpt','mvp'))
    if 'draftkings' in site or site == 'dk': return 'DK_SHOWDOWN' if single else 'DK_CLASSIC'
    if 'fanduel' in site or site == 'fd': return 'FD_SINGLE' if single else 'FD_FULL'
    raise ValueError('Choose DraftKings or FanDuel; platform could not be verified')


def slot_key(value):
    value = str(value).upper().strip()
    value = re.sub(r'\.\d+$','',value)
    value = re.sub(r'\d+$','',value)
    return 'CPT' if value == 'CAPTAIN' else 'FLEX' if value in {'UTIL','ANYFLEX'} else value


def parse_lineups(frame):
    lookup = {str(c).strip().casefold(): c for c in frame.columns}
    entry_col = next((lookup[k] for k in ('entryid','entry id') if k in lookup), None)
    source = frame.drop_duplicates(entry_col) if entry_col else frame
    output = []
    if 'lineup' in lookup:
        for raw in source[lookup['lineup']].dropna():
            pairs = [(slot_key(slot),name.strip(' ,;|')) for slot,name in TOKEN.findall(str(raw))]
            if pairs: output.append(pairs)
    else:
        cols = [(c,slot_key(c)) for c in frame.columns if slot_key(c) in SLOTS]
        for row in source.to_dict('records'):
            pairs = [(slot,str(row[c]).strip()) for c,slot in cols if pd.notna(row[c]) and str(row[c]).strip()]
            if pairs: output.append(pairs)
    valid = []
    for pairs in output:
        keys = [name_key(name) for _,name in pairs]
        if 5 <= len(pairs) <= 9 and all(keys) and len(keys)==len(set(keys)):
            valid.append(pairs)
    return valid


def features_from_lineups(lineups, metadata=None, salary_cap=50000, ownership=None):
    """Use verified historical metadata only; never substitute today's salaries."""
    metadata = metadata or {}
    total = len(lineups)
    if not total: return pd.DataFrame()
    if ownership is None:
        counts = Counter(name_key(name) for lineup in lineups for _,name in lineup)
        ownership = {key: 100*count/total for key,count in counts.items()}
    # Captain concentration transfers across slates without persisting player
    # identity. Derive it from the complete proposal/standings population.
    captains=Counter(name_key(name) for lineup in lineups for slot,name in lineup if slot in {'CPT','MVP'})
    captain_total=sum(captains.values())
    records=[]
    for lineup in lineups:
        names=[name_key(name) for _,name in lineup]
        own=np.array([ownership.get(name,0) for name in names],float)
        record={'ownership_sum':float(own.sum()),
                'ownership_product_log':float(np.log(np.clip(own/100,.00001,1)).sum())}
        captain=next((name_key(name) for slot,name in lineup if slot in {'CPT','MVP'}),None)
        if captain is not None and captain_total:
            record['captain_popularity']=100*captains[captain]/captain_total
        rows=[metadata.get(name,{}) for name in names]
        salaries=[row.get('Salary') for row in rows]
        if all(value is not None and pd.notna(value) for value in salaries):
            used=sum(float(value)*(1.5 if slot in {'CPT','MVP'} else 1) for (slot,_),value in zip(lineup,salaries))
            record['salary_left']=salary_cap-used
        elif metadata.get('__lineup_salaries__') is not None:
            record['salary_left']=salary_cap-metadata['__lineup_salaries__'][len(records)]
        qb=next((row for (slot,_),row in zip(lineup,rows) if slot=='QB'),{})
        if isinstance(qb.get('Team'),str) and qb['Team'].strip() and all(isinstance(row.get('Team'),str) and row['Team'].strip() and isinstance(row.get('Position'),str) and row['Position'].strip() for row in rows):
            team,opp=qb['Team'],qb.get('Opponent')
            record['qb_pass_catcher_stack_count']=sum(row['Team']==team and row['Position'] in {'WR','TE'} for row in rows)
            if opp: record['bring_back_count']=sum(row['Team']==opp and row['Position'] in {'RB','WR','TE'} for row in rows)
            defenses={row['Team'] for row in rows if row['Position'] in {'D','DST','DEF'}}
            record['rb_dst_stack']=int(any(row['Position']=='RB' and row['Team'] in defenses for row in rows))
        records.append(record)
    return pd.DataFrame(records)


def summarize(features):
    result={}
    for key,edges in BINS.items():
        if key not in features: continue
        vals=pd.to_numeric(features[key],errors='coerce').dropna().to_numpy(float)
        vals=vals[np.isfinite(vals)]
        if not len(vals): continue
        # Clip tails into edge bins; never discard outliers from the counts.
        hist=np.histogram(np.clip(vals,edges[0],edges[-1]-.000001),bins=edges)[0]
        result[key]={'count':len(vals),'mean':float(vals.mean()),'std':float(vals.std()),
                     'edges':edges.tolist(),'counts':hist.tolist()}
    return result


def verified_fanduel_mvp_first(frame, lineups):
    """Recognize FD positional-token Single Game exports using score evidence.

    First-listed MVP is accepted only when every complete roster's published
    score equals 1.5 times its first player's base FPTS plus five FLEX scores.
    Scores establish export schema only; they are never model features.
    """
    required={'Player','FPTS','Points','Lineup'}
    if not required <= set(frame.columns):
        raise ValueError('Cannot verify first-listed FanDuel MVP without player and lineup scores')
    player_scores={}
    for name,points in frame[['Player','FPTS']].itertuples(index=False,name=None):
        if pd.isna(name) or pd.isna(points):continue
        key=name_key(name);value=float(points)
        if not np.isfinite(value) or (key in player_scores and abs(player_scores[key]-value)>1e-6):
            raise ValueError('Conflicting FanDuel player scores')
        player_scores[key]=value
    roster_scores={}
    for raw,points in frame[['Lineup','Points']].itertuples(index=False,name=None):
        if pd.isna(raw) or pd.isna(points):continue
        keys=tuple(name_key(name.strip(' ,;|')) for _,name in TOKEN.findall(str(raw)))
        value=float(points)
        if keys in roster_scores and abs(roster_scores[keys]-value)>.02:
            raise ValueError('Conflicting FanDuel lineup scores')
        roster_scores[keys]=value
    for row in lineups:
        keys=tuple(name_key(name) for _,name in row)
        if len(keys)!=6 or not all(key in player_scores for key in keys) or keys not in roster_scores:
            raise ValueError('Incomplete score evidence for first-listed FanDuel MVP')
        expected=sum(player_scores[key] for key in keys)+.5*player_scores[keys[0]]
        if not np.isfinite(roster_scores[keys]) or abs(expected-roster_scores[keys])>.02:
            raise ValueError('First-listed FanDuel MVP does not reconcile to lineup points')
    return [[('MVP',row[0][1])]+[('FLEX',name) for _,name in row[1:]] for row in lineups]


def ingest_frames(frames, digest, platform='Auto', mode='Auto', fee=None, max_entries=None, metadata=None, game_count=None):
    profiles=[]
    for index,frame in enumerate(frames):
        rank_columns={str(c).strip().casefold() for c in frame.columns}
        if not rank_columns.intersection({'rank','place','placement','finish'}):
            raise ValueError('Completed standings need a Rank/Place column; a generated lineup export is not field history')
        lineups=parse_lineups(frame)
        if not lineups: continue
        site=platform
        if str(site).casefold()=='auto':
            cols={str(c).replace(' ','').casefold() for c in frame.columns}
            # FanDuel exports also use EntryId/EntryName. Slate-prefixed
            # player IDs identify FD; shared entry headers do not identify DK.
            if any(re.search(r'\(\d+-\d+\)',name) for row in lineups for _,name in row): site='FanDuel'
            elif 'EntryId' in frame.columns and 'EntryName' in frame.columns: site='DraftKings'
            elif any(slot=='MVP' for slot,_ in lineups[0]): site='FanDuel'
            elif any(slot=='CPT' for slot,_ in lineups[0]): site='DraftKings'
            else: raise ValueError('Select the source platform for this standings file')
        if ('fanduel' in str(site).casefold() or str(site).casefold()=='fd') and all(
                len(row)==6 and not any(slot in {'CPT','MVP'} for slot,_ in row) for row in lineups):
            if str(mode).casefold() in {'auto','single game'}:
                lineups=verified_fanduel_mvp_first(frame,lineups)
        inferred=mode
        if str(mode).casefold()=='auto':
            inferred='Single Game' if any(slot in {'CPT','MVP'} for slot,_ in lineups[0]) else 'Full Roster'
        fmt=format_key(site,inferred)
        if fmt=='DK_SHOWDOWN' and any(sum(slot=='CPT' for slot,_ in row)!=1 or any(slot=='MVP' for slot,_ in row) for row in lineups):
            raise ValueError('DraftKings Showdown standings must have one CPT, not MVP')
        if fmt=='FD_SINGLE' and any(sum(slot=='MVP' for slot,_ in row)!=1 or any(slot=='CPT' for slot,_ in row) for row in lineups):
            raise ValueError('FanDuel Single Game standings must have one MVP, not CPT')
        if fmt in {'DK_CLASSIC','FD_FULL'} and any(sum(slot=='QB' for slot,_ in row)!=1 for row in lineups):
            raise ValueError('Full-roster NFL standings must have exactly one QB')
        expected=6 if fmt=='DK_SHOWDOWN' else 9 if fmt in {'DK_CLASSIC','FD_FULL'} else None
        if expected and any(len(row)!=expected for row in lineups):
            raise ValueError('Standings roster size does not match selected format')
        sizes={len(row) for row in lineups}
        if len(sizes)!=1: raise ValueError('Mixed roster sizes must be imported separately')
        cap=60000 if fmt.startswith('FD') else 50000
        feats=features_from_lineups(lineups,metadata,cap)
        canonical=[tuple(sorted((slot if slot in {'CPT','MVP'} else 'PLAYER',name_key(name)) for slot,name in row)) for row in lineups]
        duplicates=Counter(canonical)
        id_column = next((c for c in frame.columns if str(c).replace(' ','').casefold()=='entryid'),None)
        if id_column is not None:
            # Same completed contest imported as ZIP/CSV or reordered rows must
            # not become multiple training contests. Persist only the digest.
            identifiers=sorted(set(frame[id_column].dropna().astype(str).str.replace(r'^(\d+)\.0$',r'\1',regex=True)))
            profile_id=hashlib.sha256((fmt+'|'+ '|'.join(identifiers)).encode()).hexdigest()
        else:
            profile_id=digest+':'+str(index)
        profiles.append({'id':profile_id,'format':fmt,'sport':'NFL',
            'stake_bucket':stake_bucket(fee),'max_entries':max_entries,
            'roster_size':next(iter(sizes)),'game_count':game_count,'lineups':len(lineups),
            'unique_lineups':len(duplicates),'mean_copies':len(lineups)/len(duplicates),
            'features':summarize(feats),'imported_at':datetime.now(timezone.utc).isoformat()})
        if {'qb_pass_catcher_stack_count','bring_back_count'} <= set(feats.columns):
            paired=feats[['qb_pass_catcher_stack_count','bring_back_count']].dropna()
            if len(paired):
                labels=np.minimum(paired.iloc[:,0].to_numpy(int),2)*2+(paired.iloc[:,1].to_numpy(int)>0)
                profiles[-1]['joint_stack_bringback']={'counts':np.bincount(labels,minlength=6).tolist(),
                    'supported_lineups':len(paired),'grouping':'stack 0/1/2+ crossed with bring-back 0/1+'}
    if not profiles: raise ValueError('No complete lineups were found; no learning was applied')
    return profiles


def read_standings(raw, filename):
    if str(filename).lower().endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            return [pd.read_csv(z.open(name),low_memory=False) for name in z.namelist() if name.lower().endswith('.csv')]
    return [pd.read_csv(io.BytesIO(raw),low_memory=False)]


def merge_stores(*stores):
    contests={}
    for store in stores:
        if not store: continue
        if store.get('schema')!=SCHEMA: raise ValueError('Unsupported field-history schema')
        for contest in store.get('contests',[]):
            if not isinstance(contest,dict) or not contest.get('id') or not contest.get('features'):
                raise ValueError('Invalid field-history profile')
            # Validate values used by field calibration, including imported backups.
            for key,feature in contest['features'].items():
                edges=np.asarray(feature.get('edges',[]),float);counts=np.asarray(feature.get('counts',[]),float)
                if key not in BINS or not np.array_equal(edges,BINS[key]) or len(counts)!=len(edges)-1 or not np.isfinite(counts).all() or (counts<0).any():
                    raise ValueError('Invalid field-history histogram')
            previous=contests.get(contest['id'])
            if previous:
                if previous.get('format')!=contest.get('format'):
                    raise ValueError('A field-history identity has conflicting formats')
                contest=dict(contest,features={**previous['features'],**contest['features']})
                if contest.get('stake_bucket')=='UNKNOWN':contest['stake_bucket']=previous.get('stake_bucket','UNKNOWN')
                if contest.get('max_entries') is None:contest['max_entries']=previous.get('max_entries')
            contests[contest['id']]=contest
    return {'schema':SCHEMA,'contests':list(contests.values())}


def load_store(path):
    path=Path(path)
    return merge_stores(json.loads(path.read_text())) if path.exists() else {'schema':SCHEMA,'contests':[]}


def save_store(path,store):
    store=merge_stores(store)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.field-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as handle: json.dump(store,handle,allow_nan=False)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def matching_profiles(store,platform,mode,fee=None,max_entries=None,roster_size=None,game_count=None):
    fmt=format_key(platform,mode)
    profiles=[c for c in store.get('contests',[]) if c['format']==fmt and c.get('sport')=='NFL' and (roster_size is None or c.get('roster_size')==roster_size)]
    profiles=[c for c in profiles if c.get('game_count') is None or c.get('game_count')==game_count]
    if fee is not None:
        exact=[c for c in profiles if c.get('stake_bucket')==stake_bucket(fee)]
        profiles=exact or [c for c in profiles if c.get('stake_bucket')=='UNKNOWN']
    if max_entries is not None:
        exact=[c for c in profiles if c.get('max_entries')==max_entries]
        profiles=exact or [c for c in profiles if c.get('max_entries') is None]
    return profiles


def calibrate_field(field,pool,slots,profiles,target,rng):
    """Select from an oversized legal field without adding artificial duplicate rows.

    Learned/source density ratios are bounded and mixed with a uniform floor.
    Counts are learned per contest and averaged, so a huge contest cannot erase
    all smaller contests. Player identity is never transferred across slates.
    """
    if field.empty or not profiles or len(field)<=target:
        return field.head(target).copy(),{'applied':False,'reason':'No matching profile or insufficient proposal surplus'}
    lineups=[list(zip([slot_key(slot) for slot in slots],row)) for row in field[slots].itertuples(index=False,name=None)]
    meta={name_key(row['Name']):dict(row,Position=str(row.get('Position','')).upper().split('/')[0]) for row in pool.to_dict('records')}
    if 'Salary' in field:meta['__lineup_salaries__']=field['Salary'].to_numpy(float)
    features=features_from_lineups(lineups,meta,60000 if profiles[0]['format'].startswith('FD') else 50000)
    log_weight=np.zeros(len(field));used=[]
    for key,edges in BINS.items():
        candidates=[p['features'][key] for p in profiles if key in p['features']]
        if not candidates or key not in features:continue
        values=features[key].to_numpy(float)
        if not np.isfinite(values).all():continue
        bins=np.clip(np.searchsorted(edges,values,side='right')-1,0,len(edges)-2)
        source=np.bincount(bins,minlength=len(edges)-1).astype(float)+1
        source/=source.sum()
        learned=np.mean([(np.asarray(c['counts'],float)+1)/(sum(c['counts'])+len(c['counts'])) for c in candidates],axis=0)
        log_weight+=np.log(np.clip(learned[bins]/source[bins],.25,4))
        used.append(key)
    if not used:return field.head(target).copy(),{'applied':False,'reason':'No compatible features'}
    weights=.25+.75*np.exp(np.clip(log_weight/max(len(used),1),-1.4,1.4))
    if field.attrs.get('construction_distribution') is not None:
        from simmah_field_construction import construction_quotas
        groups,quotas=construction_quotas(field,target)
        chosen=[]
        for group,quota in enumerate(quotas):
            if not quota:continue
            rows=np.flatnonzero(groups==group);w=weights[rows]
            chosen.extend(rng.choice(rows,size=quota,replace=False,p=w/w.sum()).tolist())
        chosen=np.asarray(chosen,int)
    else:
        chosen=rng.choice(len(field),size=target,replace=False,p=weights/weights.sum())
    return field.iloc[chosen].reset_index(drop=True),{'applied':True,'contests':len(profiles),
        'historical_entries':sum(p['lineups'] for p in profiles),'features':used,
        'formats':sorted({p['format'] for p in profiles}),'profile_ids':[p['id'] for p in profiles]}


def update_store(path,store):
    """Merge under a process lock so concurrent Streamlit sessions keep imports."""
    import fcntl
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_suffix(path.suffix+'.lock').open('a') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        try:
            merged=merge_stores(load_store(path),store)
            save_store(path,merged)
            return merged
        finally:
            fcntl.flock(lock.fileno(),fcntl.LOCK_UN)
