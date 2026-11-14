"""Pre-Nov6 ESPN rotation audit; never reads locked-game PBP."""
import gzip,hashlib,itertools,json,sys
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np,pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_nba_rotations import reconstruct_period
from scripts.audit_minutes_scripts_offline import seconds
from scripts.expand_minutes_evidence_offline import player_key,team_key

def convert(data):
    lookup={};actual={};teams={}
    for t in data['boxscore']['players']:
        tid=str(t['team']['id']);teams[tid]=team_key(t['team']['abbreviation'])
        for group in t['statistics']:
            for a in group['athletes']:
                pid=str(a['athlete']['id']);lookup[pid]={'name':a['athlete']['displayName'],'team':tid,'position':a['athlete'].get('position',{}).get('abbreviation','Unknown')}
                stats=dict(zip(group['labels'],a.get('stats',[])))
                if stats.get('MIN') not in [None,'']:actual[(tid,pid)]=float(stats['MIN'])*60
                elif a.get('didNotPlay') is True:actual[(tid,pid)]=0.
    periods=defaultdict(list)
    for source_order,e in enumerate(data['events']):
        period=int(e.get('period',{}).get('number',0))
        if not 1<=period<=4:continue
        s=seconds(e['clock']['displayValue']);clock=f'PT{int(s//60)}M{s%60:.6f}S';typ=e.get('type',{}).get('text','');ps=[str(p['athlete']['id']) for p in e.get('participants',[])];order=source_order*10
        base=dict(period=period,clock=clock,orderNumber=order,actionType='other',teamId='',personId='')
        if typ=='Substitution':
            if len(ps)!=2 or any(p not in lookup for p in ps) or lookup[ps[0]]['team']!=lookup[ps[1]]['team']:raise ValueError('Unresolved substitution identity')
            if ' enters the game for ' not in e.get('text',''):raise ValueError('Unknown substitution wording')
            inc,out=e['text'].split(' enters the game for ',1);tid=lookup[ps[0]]['team'];team=teams[tid]
            if player_key(inc,team)!=player_key(lookup[ps[0]]['name'],team) or player_key(out,team)!=player_key(lookup[ps[1]]['name'],team):raise ValueError('Substitution text/ID mismatch')
            periods[period].extend([dict(base,actionType='substitution',subType='out',teamId=tid,personId=ps[1]),dict(base,orderNumber=order+1,actionType='substitution',subType='in',teamId=tid,personId=ps[0])])
        else:
            actor=ps[0] if ps else None
            isactor=e.get('shootingPlay') or any(x in typ.lower() for x in ['rebound','turnover','free throw','jump ball','jumpball'])
            if actor in lookup and isactor:base.update(actionType='2pt',teamId=lookup[actor]['team'],personId=actor)
            periods[period].append(base)
    if sorted(periods)!=[1,2,3,4]:raise ValueError('Incomplete regulation periods')
    stints=[];transitions=[]
    for period,rows in sorted(periods.items()):
        s,t=reconstruct_period(rows);stints.extend(s);transitions.extend(t)
    reconstructed=Counter()
    for stint in stints:
        for p in stint['players']:reconstructed[(stint['team'],p)]+=stint['seconds']
    # Source MIN is rounded whole minutes; do not call this exact boxscore parity.
    if any(k not in actual or abs(v-actual[k])>60.01 for k,v in reconstructed.items()):raise ValueError('Player minute mismatch beyond whole-minute source resolution')
    if any(v>60.01 and k not in reconstructed for k,v in actual.items()):raise ValueError('Played athlete absent from reconstructed floor')
    return lookup,teams,stints,transitions,max((abs(v-actual[k]) for k,v in reconstructed.items()),default=0.)

def run(root):
    root=Path(root);out=root/'earlier-recipient-results';out.mkdir(exist_ok=True)
    # Read metadata labels only to enforce disjointness; never open evaluation PBP.
    ctx=pd.read_csv(root/'minutes-script-results/primary_context.csv',dtype={'game_id':str,'package':str})
    locked=set(ctx.loc[ctx.date>='2026-11-06','game_id']);training=ctx[(ctx.date<'2026-11-06')&(ctx.overtimes==0)].copy()
    truth={(str(r.game_id),r.team_key,r.name_key):r for r in training.itertuples()}
    accepted=[];rejected=[];transitions=[];deficit=[];units=[];source=[]
    for path in sorted((root/'simmah-nba-clock/data/nba_pbp').glob('*/*.json.gz')):
        if path.parent.name>='2026-11-06':continue
        # Filename guard before opening any game bytes.
        if path.name.removesuffix('.json.gz') in locked:raise AssertionError('Locked game opened')
        raw=path.read_bytes();d=json.loads(gzip.decompress(raw));gid=str(d['event_id'])
        if gid in locked or d['date']>='2026-11-06':raise AssertionError('Temporal boundary violation')
        if max(e.get('period',{}).get('number',0) for e in d['events'])>4:
            rejected.append({'game_id':gid,'reason':'OT excluded'});continue
        try:lookup,teams,stints,tr,maxerr=convert(d)
        except (ValueError,KeyError,TypeError) as exc:
            rejected.append({'game_id':gid,'reason':str(exc)});continue
        accepted.append({'game_id':gid,'date':d['date'],'maximum_rounding_residual_seconds':maxerr})
        source.append({'game_id':gid,'sha256':hashlib.sha256(raw).hexdigest()})
        for s in stints:units.append(dict(s,game_id=gid,team=teams[s['team']]))
        for t in tr:
            team=teams[t['team']];item={'game_id':gid,'date':d['date'],'team':team,'period':t['period'],'clock':t['clock'],'out':[lookup[p]['name'] for p in t['out']],'in':[lookup[p]['name'] for p in t['in']],'out_position':[lookup[p]['position'] for p in t['out']],'in_position':[lookup[p]['position'] for p in t['in']]};transitions.append(item)
            for p in t['out']:
                name=player_key(lookup[p]['name'],team)[0];r=truth.get((gid,team,name))
                if r is not None and r.projected_minutes>=28 and r.delta< -5:
                    deficit.append(dict(item,core_name=name,projected_minutes=r.projected_minutes,actual_minutes=r.actual_minutes,blowout_proxy=bool(r.blowout_proxy),foul_threshold_proxy=bool(r.foul_threshold_proxy),unambiguous_single=len(t['out'])==len(t['in'])==1))
    counts=Counter()
    for t in transitions:
        if len(t['out'])==len(t['in'])==1:counts[(t['team'],t['out'][0],t['in'][0])]+=1
    patterns=[]
    for (team,donor),group in itertools.groupby(sorted(counts),key=lambda k:k[:2]):
        options=[(k[2],counts[k]) for k in group];options.sort(key=lambda k:(-k[1],k[0]));total=sum(n for _,n in options)
        patterns.append({'team':team,'donor':donor,'events':total,'recipients':[{'name':n,'count':c,'probability':c/total} for n,c in options],'top1_share':options[0][1]/total,'top2_share':sum(c for _,c in options[:2])/total})
    singles=[t for t in deficit if t['unambiguous_single']];bycore=[]
    for key,rows in itertools.groupby(sorted(singles,key=lambda r:(r['game_id'],r['team'],r['core_name'])),key=lambda r:(r['game_id'],r['team'],r['core_name'])):
        rows=list(rows);c=Counter(r['in'][0] for r in rows);total=sum(c.values());bycore.append({'game_id':key[0],'team':key[1],'core_name':key[2],'single_exit_events':total,'recipients':dict(c),'top2_share':sum(n for _,n in c.most_common(2))/total})
    result={'offline_only':True,'cutoff':'2026-11-06','locked_games_not_opened':len(locked),'training_forecast_games':training.game_id.nunique(),'accepted_earlier_games':len(accepted),'rejected_earlier_games':len(rejected),'joint_transition_events':len(transitions),'single_exit_events':sum(counts.values()),'core_deficit_exit_events':len(deficit),'unambiguous_core_deficit_exit_events':len(singles),'core_deficit_player_games_with_single_exits':len(bycore),'all_single_donor_weighted_top2_share':float(np.average([p['top2_share'] for p in patterns],weights=[p['events'] for p in patterns])) if patterns else None,'rejections_by_reason':dict(Counter(r['reason'] for r in rejected)),'limitations':['Single substitutions identify immediate replacements, not causal attribution of all lost core minutes','Joint transitions are preserved as sets; no invented donor-to-recipient pairing','Whole-minute ESPN boxscore resolution permits up to60.01-second per-player residual, not exact timing verification','Earlier PBP without frozen forecasts trains replacement patterns only, not >5-minute projected-miss labels','No evaluation-game data opened or co-spike-target fitting; observed10.2% is not a training objective']}
    for name,value in [('summary',result),('accepted',accepted),('rejected',rejected),('sources',source),('transitions',transitions),('core_deficit_exits',deficit),('core_deficit_player_games',bycore),('recipient_patterns',patterns)]:
        (out/(name+'.json')).write_text(json.dumps(value,indent=2))
    print(json.dumps(result,indent=2))
if __name__=='__main__':run(sys.argv[1])
