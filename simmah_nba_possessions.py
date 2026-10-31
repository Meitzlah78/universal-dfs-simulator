"""Conservative NBA possession reconstruction from ESPN event sequences.

Ambiguous transitions are flagged for review, never silently treated as clean
training examples. This does not infer five-man lineups or coaching rotations.
"""
import re


def reconstruct(game):
    events=game['events']
    team_ids=sorted({str(e.get('team',{}).get('id')) for e in events if e.get('team',{}).get('id')})
    if len(team_ids)!=2:raise ValueError('Two event teams are required')
    def other(team):return next(t for t in team_ids if t!=team)
    def kind(e):return str(e.get('type',{}).get('text','')).lower()
    def team(e):return str(e.get('team',{}).get('id',''))
    def clock(e):return (e.get('period',{}).get('number'),e.get('clock',{}).get('displayValue'))
    def ft(e):return 'free throw' in kind(e)
    def shot(e):return bool(e.get('shootingPlay')) and not ft(e)
    def made(e):return bool(e.get('scoringPlay')) and float(e.get('scoreValue',0))>0
    def turnover(e):return 'turnover' in kind(e) or kind(e) in {'traveling','offensive charge'}
    results=[];current=None
    def start(offense,e):
        return {'offense':offense,'period':e.get('period',{}).get('number'),
            'start_clock':e.get('clock',{}).get('displayValue'),'event_ids':[],
            'points':0,'flags':[]}
    def close(reason):
        nonlocal current
        if current is not None:
            current['end_reason']=reason
            results.append(current)
            current=None
    for i,e in enumerate(events):
        k=kind(e);t=team(e)
        if current and e.get('period',{}).get('number')!=current['period']:
            current['flags'].append('missing_period_end');close('period_change')
        if k in {'end period','end game'}:
            if current:current['event_ids'].append(str(e['id']))
            close('period_end');continue
        is_offense=shot(e) or ft(e) or turnover(e) or k=='offensive rebound'
        if not is_offense and k!='defensive rebound':
            if current:
                current['event_ids'].append(str(e['id']))
                if 'challenge' in k or 'review' in k or 'jumpball' in k:
                    current['flags'].append('review_or_jump_ball')
            continue
        if t not in team_ids:continue
        offense=other(t) if k=='defensive rebound' else t
        if current and current['offense']!=offense:
            current['flags'].append('unexplained_control_change');close('inferred_change')
        if current is None:
            current=start(offense,e)
            if k in {'offensive rebound','defensive rebound'}:
                current['flags'].append('missing_prior_shot')
        current['event_ids'].append(str(e['id']))
        if made(e):current['points']+=int(e.get('scoreValue',0))
        if k=='defensive rebound':close('defensive_rebound')
        elif turnover(e):close('turnover')
        elif shot(e) and made(e):
            # A same-clock foul/and-one trip belongs to the made-shot possession.
            following=[]
            for next_event in events[i+1:]:
                if clock(next_event)!=clock(e):break
                following.append(next_event)
            and_one=any(ft(n) and team(n)==t and re.search(r'1 of 1',kind(n)) for n in following)
            if not and_one:close('made_field_goal')
        elif ft(e):
            if 'technical' in k or 'technical' in str(e.get('text','')).lower() or 'flagrant' in k:
                current['flags'].append('retained_possession_free_throw')
                continue
            trip=re.search(r'(\d+) of (\d+)',k)
            if not trip:
                current['flags'].append('unknown_free_throw_trip')
            elif trip[1]==trip[2] and made(e):close('final_free_throw')
    if current:
        current['flags'].append('unterminated_possession');close('end_of_data')
    for row in results:
        row['flags']=sorted(set(row['flags']))
        row['usable']=not row['flags']
    return results
