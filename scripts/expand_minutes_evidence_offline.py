"""Add explicitly frozen pre-tip forecasts; missing actuals never become zero."""
import argparse,gzip,hashlib,io,json,sys,zipfile
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from simmah_nba_projections import player_key as _player_key,team_key as _team_key
from simmah_nba_scoring import score_nba


def team_key(value):
    value=str(value).upper().strip()
    return _team_key({'UTAH':'UTA','WSH':'WAS'}.get(value,value))


def player_key(name,team):return _player_key(name,team_key(team))


def snapshot_keys(package,frame):
    return set(zip(frame.package.astype(str),frame.player_id.astype(str)))


def run(audit,pbp,nov13,archives,output):
    output=Path(output);output.mkdir(exist_ok=True,parents=True)
    with zipfile.ZipFile(audit) as z:
        actual_rows=json.loads(z.read('actual-player-games.json'))
        original=pd.read_csv(io.BytesIO(z.read('player-forecast-audit.csv')),dtype={'package':str,'game_id':str,'player_id':str})
    actuals={};games={}
    for row in actual_rows:
        name='Gregory Jackson' if row['name']=='GG Jackson' else row['name']
        key=(str(row['game_id']),player_key(name,row['team']))
        if key in actuals:raise ValueError('Ambiguous historical actuals')
        actuals[key]=row
    for path in sorted(Path(pbp).glob('*/*.json.gz')):
        with gzip.open(path,'rt') as f:game=json.load(f)
        event=str(game['event_id']);opening=[pd.Timestamp(p['wallclock']) for p in game['events'] if p.get('wallclock') and p.get('period',{}).get('number',0)>=1]
        if not opening:continue
        teams={team_key(t['team']['abbreviation']) for t in game['boxscore']['players']}
        games[event]={'date':game['date'],'teams':teams,'opening':min(opening),'margin':abs(game['home_score']-game['away_score']),
            'overtimes':max(e.get('period',{}).get('number',0) for e in game['events'])-4,'source':str(path)}
    for path in sorted(Path(nov13).glob('401*.json.gz')):
        with gzip.open(path,'rt') as f:data=json.load(f)
        c=data['header']['competitions'][0]
        if not c['status']['type']['completed']:raise ValueError('Unfinished game')
        event=str(data['header']['id']);teams={team_key(t['team']['abbreviation']) for t in c['competitors']}
        opening=[pd.Timestamp(p['wallclock']) for p in data.get('plays',[]) if p.get('wallclock') and p.get('period',{}).get('number',0)>=1]
        if not opening:continue
        date=pd.Timestamp(c['date']).tz_convert('America/New_York').date().isoformat()
        periods=max((p.get('period',{}).get('number',0) for p in data.get('plays',[])),default=0)
        if periods<4:raise ValueError('Completed-game period ledger unavailable')
        ot=periods-4
        games[event]={'date':date,'teams':teams,'opening':min(opening),'margin':abs(int(c['competitors'][0]['score'])-int(c['competitors'][1]['score'])),
            'overtimes':ot,'source':str(path)}
        for t in data['boxscore']['players']:
            for g in t['statistics']:
                for p in g['athletes']:
                    name=p['athlete']['displayName'];name='Gregory Jackson' if name=='GG Jackson' else name
                    if p['stats']:
                        s=dict(zip(g['labels'],p['stats']));minutes=float(s['MIN']);dnp=False
                        vals={k:float(s[k]) for k in ['PTS','REB','AST','STL','BLK','TO','PF']}
                        vals.update(FGM=float(s['FG'].split('-')[0]),PM3=float(s['3PT'].split('-')[0]),FTM=float(s['FT'].split('-')[0]))
                    elif p.get('didNotPlay') is True:
                        minutes=0.;dnp=True;vals=dict.fromkeys(['PTS','FGM','PM3','FTM','REB','AST','STL','BLK','TO','PF'],0.)
                    else:continue
                    actuals[(event,player_key(name,t['team']['abbreviation']))]={'game_id':event,'date':date,'name':name,'team':team_key(t['team']['abbreviation']),
                        'MIN':minutes,'dnp':dnp,'overtimes':ot,**vals}
    forecasts=[];omissions=[];sources=[]
    for path in archives:
        path=Path(path)
        with zipfile.ZipFile(path) as o:raw=o.read('original_build.zip') if 'original_build.zip' in o.namelist() else path.read_bytes()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            manifest=json.loads(z.read('manifest.json'))
            for n,m in manifest['files'].items():
                if hashlib.sha256(z.read(n)).hexdigest()!=m['sha256']:raise ValueError('Archive hash mismatch')
            meta=json.loads(z.read('inputs/player_pool.json'));pool=pd.DataFrame(meta['rows']);contest=json.loads(z.read('inputs/contest.json'));package=str(contest['id'])
            if package in set(original.package):raise ValueError('Existing package is not new evidence')
            captured=pd.Timestamp(manifest['captured_at_utc']);platform=contest['platform'];date=contest['date']
            with np.load(io.BytesIO(z.read('solver/arrays.npz'))) as arrays:draws=arrays['outcomes_seed_2100'].copy()
        sources.append({'package':package,'platform':platform,'date':date,'archive':str(path),'sha256':hashlib.sha256(raw).hexdigest()})
        for i,p in pool.iterrows():
            try:projection=float(p.Projection);minutes=float(p['Projected Minutes'])
            except (ValueError,TypeError):continue
            if not np.isfinite([projection,minutes]).all() or projection<=0 or not 0<minutes<=48 or str(p['Injury Status']).upper() in ['OUT','O','IR','SUSPENDED']:continue
            matches=[(event,g) for event,g in games.items() if g['date']==date and g['teams']=={team_key(p.Team),team_key(p.Opponent)}]
            if len(matches)!=1:
                omissions.append({'package':package,'name':p.Name,'reason':'missing/ambiguous completed game'});continue
            event,game=matches[0]
            if captured>=game['opening']:
                omissions.append({'package':package,'name':p.Name,'reason':'capture not before observed opening'});continue
            actual=actuals.get((event,player_key(p.Name,p.Team)))
            if actual is None:
                omissions.append({'package':package,'name':p.Name,'reason':'missing/ambiguous explicit actual player'});continue
            vals={k:np.asarray(actual[src]) for k,src in [('fgm','FGM'),('threes','PM3'),('ftm','FTM'),('rebounds','REB'),('assists','AST'),('steals','STL'),('blocks','BLK'),('turnovers','TO')]}
            points=float(score_nba(platform,**vals));q=np.quantile(draws[:,i],[.01,.1,.5,.9,.95,.99])
            forecasts.append(dict(package=package,date=date,platform=platform,game_id=event,name=p.Name,team=p.Team,opponent=p.Opponent,
                player_id=str(p['Player ID']),captured_at=captured.isoformat(),observed_opening_utc=game['opening'].isoformat(),
                source_projection=projection,mean=float(draws[:,i].mean()),sd=float(draws[:,i].std()),
                **dict(zip(['p01','p10','p50','p90','p95','p99'],q)),actual=points,projected_minutes=minutes,actual_minutes=actual['MIN'],
                overtimes=actual['overtimes'],explicit_dnp=actual['dnp'],variable_minutes=bool(meta['attrs'].get('nba_variable_minutes')),
                wider_minutes=bool(meta['attrs'].get('nba_wider_minutes'))))
    new=pd.DataFrame(forecasts);new.to_csv(output/'additional_forecasts.csv',index=False)
    if new.empty:raise ValueError('No eligible new forecasts')
    if snapshot_keys('',original)&snapshot_keys('',new):raise ValueError('Duplicate forecast package/player')
    merged=pd.concat([original,new],ignore_index=True);merged.to_csv(output/'expanded_forecasts.csv',index=False)
    context=[]
    for (event,pk),a in actuals.items():
        g=games.get(event)
        if g:context.append({'game_id':event,'name_key':pk[0],'team_key':pk[1],'actual_minutes':a['MIN'],
            'personal_fouls':a['PF'],'explicit_dnp':a['dnp'],'final_margin':g['margin']})
    pd.DataFrame(context).to_csv(output/'actual_context.csv',index=False)
    summary={'existing_forecasts':len(original),'additional_forecasts':len(new),'expanded_forecasts':len(merged),
        'existing_games':original.game_id.nunique(),'expanded_games':merged.game_id.nunique(),'additional_sources':sources,'omissions':omissions,
        'new_actual_points_source':'reconstructed from completed ESPN boxscore stats, not site-settled payouts',
        'status':'retrospective development extension under unchanged frozen policy; not a fresh prospective holdout'}
    (output/'expansion.json').write_text(json.dumps(summary,indent=2));print(json.dumps({k:v for k,v in summary.items() if k not in ['omissions','additional_sources']},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('audit');p.add_argument('pbp');p.add_argument('nov13');p.add_argument('output');p.add_argument('archives',nargs='+');a=p.parse_args();run(a.audit,a.pbp,a.nov13,a.archives,a.output)
