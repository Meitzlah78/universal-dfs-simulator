"""Sample broad historical ESPN rotation coverage without changing live models."""
import argparse
import csv
from concurrent.futures import ThreadPoolExecutor
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import sys
from urllib.request import urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_nba_history import completed_games,parse_game
from simmah_nba_rotations import reconstruct_rotations

DATES=[f'{year}-{month}-{day}' for year in (2023,2024,2025,2026)
       for month,day in [('01','15'),('03','15'),('04','25'),('06','01')]]


def audit(cache,workers=3):
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    def schedule(day):
        try:return day,completed_games(day,'2026-10-20'),None
        except Exception as exc:return day,[],type(exc).__name__+': '+str(exc)
    schedules=list(ThreadPoolExecutor(workers).map(schedule,DATES))
    ids=list(dict.fromkeys(i for _,group,_ in schedules for i in group))
    print('Discovered',len(ids),'games across',len(DATES),'sample dates',flush=True)
    def game(eid):
        try:
            path=cache/(eid+'.json')
            if path.exists():raw=path.read_bytes()
            else:
                with urlopen('https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event='+eid,timeout=15) as r:raw=r.read()
                path.write_bytes(raw)
            payload=json.loads(raw);g=parse_game(payload,eid,'2026-10-20')
            reconstructed=reconstruct_rotations(g)
            periods=sorted(set(int(e['period']['number']) for e in g['events']))
            teams={str(t['team']['id']):t['team']['displayName'] for t in g['boxscore']['players']}
            totals={};minute_checks={}
            for group in g['boxscore']['players']:
                tid=str(group['team']['id']);pids=[str(a['athlete']['id']) for s in group['statistics'] for a in s['athletes']]
                totals[tid]=sum(reconstructed['player_minutes'].get(pid,0) for pid in pids)
                expected=240+25*(max(periods)-4)
                minute_checks[tid]=abs(totals[tid]-expected)<1e-6
            deviations=[]
            for group in g['boxscore']['players']:
                for section in group['statistics']:
                    names=section.get('names',[])
                    if 'MIN' not in names:continue
                    for athlete in section.get('athletes',[]):
                        stats=athlete.get('stats',[])
                        if not stats or athlete.get('didNotPlay'):continue
                        raw_min=str(stats[names.index('MIN')])
                        if raw_min in {'','--'}:continue
                        parts=raw_min.split(':')
                        box_minutes=float(parts[0])+(float(parts[1])/60 if len(parts)==2 else 0)
                        pid=str(athlete['athlete']['id'])
                        deviations.append(abs(reconstructed['player_minutes'].get(pid,0)-box_minutes))
            max_deviation=max(deviations) if deviations else None
            contiguous=periods==list(range(1,max(periods)+1)) and max(periods)>=4
            accepted=reconstructed['complete'] and contiguous and len(teams)==2 and all(minute_checks.values()) and max_deviation is not None and max_deviation<=1.01
            return {'event_id':eid,'date':g['date'],'teams':teams,'source_sha256':hashlib.sha256(raw).hexdigest(),
                'max_box_minutes_deviation':max_deviation,'events':len(g['events']),'periods':periods,'overtimes':max(periods)-4,
                'reconstruction_complete':reconstructed['complete'],'team_minutes':totals,
                'team_budget_checks':minute_checks,'accepted':bool(accepted),'issues':reconstructed['issues']}
        except Exception as exc:return {'event_id':eid,'accepted':False,'error':type(exc).__name__+': '+str(exc)}
    games=list(ThreadPoolExecutor(workers).map(game,ids))
    accepted=[g for g in games if g['accepted']]
    years={str(y):{'available':sum(g.get('date','').startswith(str(y)) for g in games),
        'accepted':sum(g.get('date','').startswith(str(y)) for g in accepted)} for y in (2023,2024,2025,2026)}
    reasons=Counter(i['reason'] for g in games for i in g.get('issues',[]))
    return {'source':'ESPN scoreboard and summary API','dates':DATES,
        'schedule_results':[{'day':d,'games':len(ids),'error':err} for d,ids,err in schedules],
        'discovered_games':len(ids),'downloaded_and_parsed':sum('date' in g for g in games),
        'accepted_games':len(accepted),'rejected_games':len(games)-len(accepted),
        'accepted_teams':len({tid for g in accepted for tid in g['teams']}),
        'accepted_overtime_games':sum(g['overtimes']>0 for g in accepted),'by_year':years,
        'issue_counts':dict(reasons),'games':games,
        'limitations':['Purposive sample of 16 dates, not an all-season census.',
            'Same-source final-score and rotation-ledger checks, not independent verification of every player minute.',
            'ESPN player IDs still need an explicit NBA/DFS mapping.',
            'Historical actuals alone do not supply archived pregame minutes or injury news.',
            'No live model updates or predictive accuracy claims.']}


def export_minutes(report,cache,path):
    rows=[];cache=Path(cache);path=Path(path)
    for item in report['games']:
        if not item['accepted']:continue
        raw=(cache/(item['event_id']+'.json')).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=item['source_sha256']:raise ValueError('Cached source hash changed')
        game=parse_game(json.loads(raw),item['event_id'],'2026-10-20')
        reconstructed=reconstruct_rotations(game);regulation=defaultdict(float)
        for stint in reconstructed['stints']:
            if stint['period']<=4:
                for pid in stint['players']:regulation[pid]+=stint['seconds']/60
        for team in game['boxscore']['players']:
            for section in team['statistics']:
                for athlete in section['athletes']:
                    pid=str(athlete['athlete']['id']);full=reconstructed['player_minutes'].get(pid,0)
                    status='verified_dnp' if athlete.get('didNotPlay') else ('played' if full>0 else 'unresolved_zero')
                    rows.append({'ESPN Game ID':game['event_id'],'Game Date':game['date'],
                        'ESPN Team ID':str(team['team']['id']),'ESPN Player ID':pid,
                        'Name':athlete['athlete']['displayName'],'Actual Status':status,
                        'Regulation Minutes':round(regulation[pid],8),'Full Game Minutes':round(full,8),
                        'Overtime Minutes':round(full-regulation[pid],8),'Source SHA256':item['source_sha256']})
    if not rows:return {'rows':0,'file':None}
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    return {'file':path.name,'rows':len(rows),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'unresolved_zero_rows':sum(r['Actual Status']=='unresolved_zero' for r in rows),
            'id_namespace':'ESPN, not NBA or DFS'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cache',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();r=audit(a.cache)
    r['accepted_minutes_export']=export_minutes(r,a.cache,Path(a.output).with_name('accepted-player-minutes.csv'))
    Path(a.output).write_text(json.dumps(r,indent=2));print(json.dumps({k:v for k,v in r.items() if k!='games'},indent=2))
