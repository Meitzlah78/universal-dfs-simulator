"""Auditable five-player stints from NBA substitutions and box-score starters.

Periods with insufficient lineup evidence are reported as unresolved. No missing
starter is filled using salary, projection or future-game information.
"""
from collections import defaultdict


def seconds(event):
    raw=event.get('clock',{}).get('displayValue','')
    if ':' not in raw:
        return float(raw)  # ESPN uses decimal seconds near the end of periods.
    minute,second=raw.split(':')
    return 60*int(minute)+float(second)


def reconstruct_rotations(game):
    players={};starters=defaultdict(set)
    for group in game['boxscore']['players']:
        tid=str(group['team']['id'])
        for section in group.get('statistics',[]):
            for athlete in section.get('athletes',[]):
                pid=str(athlete['athlete']['id'])
                players[pid]=tid
                if athlete.get('starter'):starters[tid].add(pid)
    grouped=defaultdict(list)
    for e in game['events']:grouped[int(e['period']['number'])].append(e)
    output=[];issues=[]
    for period,events in sorted(grouped.items()):
        duration=720 if period<=4 else 300
        for tid in starters:
            changes=[];appearances=defaultdict(list)
            for i,e in enumerate(events):
                ids=[str(p['athlete']['id']) for p in e.get('participants',[]) if 'athlete' in p and 'id' in p['athlete']]
                kind=str(e.get('type',{}).get('text','')).lower()
                if kind=='substitution' and str(e.get('team',{}).get('id'))==tid:
                    if len(ids)!=2 or any(players.get(p)!=tid for p in ids):
                        changes.append((i,None,None));continue
                    changes.append((i,ids[0],ids[1]))
                elif kind!='substitution' and ('shot' in kind or 'rebound' in kind or 'turnover' in kind or 'free throw' in kind):
                    for pid in ids:
                        if players.get(pid)==tid:appearances[pid].append(i)
            if period==1:
                initial=set(starters[tid])
            else:
                initial=set()
                for pid,team_id in players.items():
                    if team_id!=tid:continue
                    first=next(((i,enter==pid) for i,enter,leave in changes if pid in {enter,leave}),None)
                    if first and not first[1]:initial.add(pid)
                    elif appearances[pid] and (first is None or appearances[pid][0]<first[0]):initial.add(pid)
            if len(initial)!=5:
                issues.append({'team':tid,'period':period,'reason':'initial_lineup_unresolved','players_found':len(initial)})
                continue
            active=set(initial);cursor=float(duration);stints=[];valid=True
            for i,enter,leave in changes:
                remaining=seconds(events[i])
                if remaining>cursor or remaining<0 or enter in active or leave not in active or players.get(enter)!=tid:
                    issues.append({'team':tid,'period':period,'reason':'invalid_substitution','event_id':events[i]['id']})
                    valid=False;break
                if cursor>remaining:
                    stints.append({'team':tid,'period':period,'seconds':cursor-remaining,'players':tuple(sorted(active))})
                active.remove(leave);active.add(enter);cursor=remaining
            if valid:
                if cursor>0:stints.append({'team':tid,'period':period,'seconds':cursor,'players':tuple(sorted(active))})
                output.extend(stints)
    minutes=defaultdict(float)
    for stint in output:
        for pid in stint['players']:minutes[pid]+=stint['seconds']/60
    return {'stints':output,'issues':issues,'player_minutes':dict(minutes),
        'complete':not issues and bool(output)}
