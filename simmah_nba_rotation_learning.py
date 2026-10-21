"""Offline empirical NBA unit/replacement baseline; never wired to live builds."""
from collections import Counter,defaultdict
from datetime import date
import math

def fit_rotation_baseline(dataset,before):
    cutoff=date.fromisoformat(before)
    games={g['game_id']:g for g in dataset['games']}
    if len(games)!=len(dataset['games']):raise ValueError('Duplicate game metadata')
    selected={gid for gid,g in games.items() if g.get('minute_verified') is True and date.fromisoformat(g['date'])<cutoff}
    if not selected:raise ValueError('Verified pre-cutoff rotation games required')
    units=Counter();patterns=Counter();fallback=Counter()
    for row in dataset['units']:
        if row['game_id'] not in games:raise ValueError('Unit has unknown game ID')
        if row['game_id'] not in selected:continue
        players=tuple(sorted(map(str,row['players'])));seconds=float(row['seconds'])
        if len(players)!=5 or len(set(players))!=5 or not math.isfinite(seconds) or seconds<=0:
            raise ValueError('Valid five-man unit and duration required')
        units[str(row['team']),players]+=seconds
    for row in dataset['transitions']:
        if row['game_id'] not in games:raise ValueError('Transition has unknown game ID')
        if row['game_id'] not in selected:continue
        out=tuple(sorted(map(str,row['out'])));inc=tuple(sorted(map(str,row['in'])))
        if not out or len(out)!=len(inc) or len(set(out))!=len(out) or len(set(inc))!=len(inc) or set(out)&set(inc):
            raise ValueError('Valid joint substitution sets required')
        team=str(row['team']);count=int(row.get('count',1))
        if count<1 or count!=row.get('count',1):raise ValueError('Positive integer transition count required')
        patterns[team,out,inc]+=count;fallback[team,len(out),inc]+=count
    unit_totals=Counter();out_totals=Counter();fallback_totals=Counter()
    for (team,players),seconds in units.items():unit_totals[team]+=seconds
    for (team,out,inc),count in patterns.items():out_totals[team,out]+=count
    for (team,size,inc),count in fallback.items():fallback_totals[team,size]+=count
    return {'schema':1,'before':before,'live_enabled':False,
        'source_archive_sha256':dataset['archive_sha256'],
        'training_games':sorted(selected),
        'units':[{'team':t,'players':list(p),'seconds':s,'probability':s/unit_totals[t]} for (t,p),s in sorted(units.items())],
        'replacements':[{'team':t,'out':list(o),'in':list(i),'count':n,
            'conditional_probability':n/out_totals[t,o],'condition_count':out_totals[t,o]} for (t,o,i),n in sorted(patterns.items())],
        'team_incoming_baseline':[{'team':t,'size':size,'in':list(i),'count':n,
            'probability':n/fallback_totals[t,size]} for (t,size,i),n in sorted(fallback.items())],
        'status':'Empirical historical baseline; conditional on observed outgoing set, not a learned exit trigger'}

def evaluate_rotation_baseline(model,dataset):
    cutoff=date.fromisoformat(model['before']);games={g['game_id']:g for g in dataset['games']}
    heldout={gid for gid,g in games.items() if g.get('minute_verified') is True and date.fromisoformat(g['date'])>=cutoff}
    if set(model['training_games'])&heldout:raise ValueError('Training/evaluation games overlap')
    choices=defaultdict(list);baseline=defaultdict(list)
    for r in model['replacements']:choices[r['team'],tuple(r['out'])].append(r)
    for r in model['team_incoming_baseline']:baseline[r['team'],r['size']].append(r)
    total=covered=correct=base_correct=common=common_correct=common_base=0
    for r in dataset['transitions']:
        if r['game_id'] not in heldout:continue
        n=int(r.get('count',1));total+=n
        key=str(r['team']),tuple(sorted(map(str,r['out'])));actual=tuple(sorted(map(str,r['in'])))
        options=choices.get(key,[]);fallback=baseline.get((key[0],len(key[1])),[])
        prediction=tuple(min(options,key=lambda p:(-p['count'],p['in']))['in']) if options else None
        base=tuple(min(fallback,key=lambda p:(-p['count'],p['in']))['in']) if fallback else None
        if options:covered+=n;correct+=n*(prediction==actual)
        if fallback:base_correct+=n*(base==actual)
        if options and fallback:
            common+=n;common_correct+=n*(prediction==actual);common_base+=n*(base==actual)
    seen_units={(u['team'],tuple(u['players'])) for u in model['units']}
    unit_seconds=known_seconds=0.
    for r in dataset['units']:
        if r['game_id'] not in heldout:continue
        seconds=float(r['seconds']);unit_seconds+=seconds
        known_seconds+=seconds*((str(r['team']),tuple(sorted(map(str,r['players'])))) in seen_units)
    return {'training_games':len(model['training_games']),'heldout_games':len(heldout),'heldout_game_ids':sorted(heldout),
        'replacement_events':total,'covered_replacement_events':covered,
        'replacement_coverage':covered/total if total else None,
        'top1_accuracy_on_covered_events':correct/covered if covered else None,
        'common_comparison_events':common,
        'conditional_model_accuracy_on_common_events':common_correct/common if common else None,
        'team_incoming_baseline_accuracy_on_common_events':common_base/common if common else None,
        'heldout_unit_seconds':unit_seconds,'seen_unit_seconds_fraction':known_seconds/unit_seconds if unit_seconds else None,
        'live_enabled':False,'limitations':'Small, nonrepresentative historical sample; outgoing set supplied from actual event. Does not predict exits, score/foul triggers, minutes, injury effects or DFS ROI.'}
