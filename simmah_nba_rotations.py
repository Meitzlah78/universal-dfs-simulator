"""Offline CDN NBA rotation reconstruction. Never changes live projections.

Five-player floor checks are necessary, not a substitute for box-score audits.
"""
import csv
import hashlib
import io
import itertools
import math
import re
import tarfile
from collections import Counter, defaultdict
from datetime import datetime


SOURCE_COMMIT='e829d4678be1e075f99e5d41a1c5f97089be446b'
SOURCE_URL=f'https://raw.githubusercontent.com/shufinskiy/nba_data/{SOURCE_COMMIT}/datasets/cdnnba_po_2025.tar.xz'
ACTOR_TYPES={'2pt','3pt','freethrow','rebound','turnover','jumpball'}


def identity(value):
    if value in (None,''):return None
    number=float(value)
    if not math.isfinite(number) or number<0 or not number.is_integer():raise ValueError('Invalid numeric ID')
    return str(int(number)) if number else None


def seconds(clock):
    m=re.fullmatch(r'PT(\d+)M([\d.]+)S',str(clock))
    if not m:raise ValueError('Invalid game clock')
    value=60*int(m[1])+float(m[2])
    if not math.isfinite(value) or value<0:raise ValueError('Invalid game clock')
    return value


def read_archive(path):
    """Read a single CSV without extracting arbitrary archive paths."""
    with tarfile.open(path,'r:xz') as archive:
        files=[m for m in archive.getmembers() if m.isfile() and m.name.endswith('.csv')]
        if len(files)!=1 or files[0].size>500_000_000:raise ValueError('Expected one bounded CSV')
        with archive.extractfile(files[0]) as stream:
            return list(csv.DictReader(io.TextIOWrapper(stream,encoding='utf-8-sig')))


def reconstruct_period(rows):
    """Infer initial floors from first sub direction and on-court actor evidence.

    Ambiguous floors or impossible replacements reject the entire period.
    Same-clock substitutions are joint transitions, never invented A->B pairs.
    """
    rows=sorted(rows,key=lambda r:float(r['orderNumber']))
    period=int(rows[0]['period']);duration=720 if period<=4 else 300
    teams={identity(r.get('teamId')) for r in rows}-{None}
    if len(teams)!=2:raise ValueError('Period does not identify exactly two teams')
    first={};members=defaultdict(set);evidence=defaultdict(set)
    for r in rows:
        team=identity(r.get('teamId'));pid=identity(r.get('personId'))
        if not team or not pid:continue
        if r['actionType']=='substitution':
            direction=r['subType']
            if direction not in {'in','out'}:raise ValueError('Unknown substitution direction')
            first.setdefault((team,pid),direction);members[team].add(pid)
        elif r['actionType'] in ACTOR_TYPES:
            members[team].add(pid)
            if (team,pid) not in first:evidence[team].add(pid)
    floors={t:{p for p in members[t] if first.get((t,p))=='out' or
               (first.get((t,p)) is None and p in evidence[t]) or
               p in evidence[t]} for t in teams}
    if any(len(f)!=5 for f in floors.values()):raise ValueError('Ambiguous period starters')
    if seconds(rows[0]['clock'])!=duration:raise ValueError('Period start clock missing')
    previous=duration;stints=[];transitions=[]
    # Source event order is retained. Clocks must never increase.
    for clock,group in itertools.groupby(rows,key=lambda r:r['clock']):
        batch=list(group);remaining=seconds(clock)
        if remaining>previous or remaining>duration:raise ValueError('Nonmonotonic period clock')
        if previous>remaining:
            for t in teams:stints.append({'team':t,'players':sorted(floors[t]),'seconds':previous-remaining,'period':period})
        # Evidence from non-sub actions is checked when no same-clock sub can
        # make its before/after ordering ambiguous.
        subs=[r for r in batch if r['actionType']=='substitution']
        if not subs:
            for r in batch:
                if r['actionType'] in ACTOR_TYPES:
                    t=identity(r.get('teamId'));p=identity(r.get('personId'))
                    if t and p and p not in floors[t]:raise ValueError('Actor absent from reconstructed floor')
        for t in teams:
            outgoing=[identity(r['personId']) for r in subs if identity(r.get('teamId'))==t and r['subType']=='out']
            incoming=[identity(r['personId']) for r in subs if identity(r.get('teamId'))==t and r['subType']=='in']
            if not outgoing and not incoming:continue
            if len(set(outgoing))!=len(outgoing) or len(set(incoming))!=len(incoming):raise ValueError('Duplicate substitution')
            if len(outgoing)!=len(incoming) or not set(outgoing)<=floors[t] or set(incoming)&floors[t]:raise ValueError('Impossible replacement set')
            before=sorted(floors[t]);floors[t]=(floors[t]-set(outgoing))|set(incoming)
            if len(floors[t])!=5:raise ValueError('Floor does not contain five players')
            transitions.append({'team':t,'period':period,'clock':remaining,'before':before,
                'after':sorted(floors[t]),'out':sorted(outgoing),'in':sorted(incoming)})
        previous=remaining
    if previous!=0:raise ValueError('Period has no final zero clock')
    return stints,transitions


def audit_rows(rows,before):
    cutoff=datetime.fromisoformat(before).date();games=defaultdict(list);rejected=[]
    for r in rows:
        # Reject future rows by actual timestamp, not the archive filename year.
        stamp=datetime.fromisoformat(r['timeActual'].replace('Z','+00:00'))
        if stamp.date()>=cutoff:continue
        games[identity(r['gameId'])].append(r)
    stints=[];transitions=[];accepted=[]
    for gid,game in games.items():
        try:
            periods=defaultdict(list)
            for r in game:periods[int(r['period'])].append(r)
            if sorted(periods)!=list(range(1,max(periods)+1)) or max(periods)<4:raise ValueError('Incomplete game periods')
            gs=[];gt=[]
            for period,events in sorted(periods.items()):
                a,b=reconstruct_period(events)
                gs.extend(dict(x,game_id=gid) for x in a);gt.extend(dict(x,game_id=gid) for x in b)
            totals=Counter()
            for s in gs:totals[s['team']]+=s['seconds']*5
            expected=5*(2880+300*(max(periods)-4))
            if len(totals)!=2 or any(abs(v-expected)>.01 for v in totals.values()):raise ValueError('Team minute conservation failed')
            stints.extend(gs);transitions.extend(gt);accepted.append(gid)
        except (ValueError,KeyError,TypeError) as exc:rejected.append({'game_id':gid,'reason':str(exc)})
    patterns=Counter((x['team'],tuple(x['out']),tuple(x['in'])) for x in transitions)
    counts=Counter()
    for (t,out,inc),n in patterns.items():counts[t,out]+=n
    together=Counter();player_seconds=Counter()
    for stint in stints:
        for player in stint['players']:player_seconds[stint['team'],player]+=stint['seconds']
        for a,b in itertools.combinations(stint['players'],2):together[stint['team'],a,b]+=stint['seconds']
    return {'schema':1,'before':before,'status':'offline candidate; box-score minute reconciliation pending',
        'live_enabled':False,
        'cooccurrence':[{'team':t,'player_a':a,'player_b':b,'shared_seconds':n,
            'fraction_a':n/player_seconds[t,a],'fraction_b':n/player_seconds[t,b]}
            for (t,a,b),n in sorted(together.items())],
        'source_games':len(games),'accepted_games':len(accepted),
        'rejected_games':rejected,'stints':stints,'transitions':transitions,
        'replacement_patterns':[{'team':t,'out':list(out),'in':list(inc),'count':n,
          'conditional_frequency':n/counts[t,out]} for (t,out,inc),n in sorted(patterns.items())]}


def _espn_clock_seconds(event):
    raw=event.get('clock',{}).get('displayValue','')
    if ':' not in raw:
        return float(raw)  # ESPN uses decimal seconds near the end of periods.
    minute,second=raw.split(':')
    return 60*int(minute)+float(second)


def reconstruct_rotations(game):
    """Reconstruct stints from the ESPN-format history and box-score starters."""
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
                remaining=_espn_clock_seconds(events[i])
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
