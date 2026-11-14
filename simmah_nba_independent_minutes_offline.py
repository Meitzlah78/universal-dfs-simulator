"""Point-in-time history-only minutes baseline. Never used by live builds."""
import numpy as np
import pandas as pd
from simmah_nba_minutes import allocate_minutes
from scripts.expand_minutes_evidence_offline import player_key


def forecast_team(roster,history,game_date,captured_at,*,history_ceiling=None):
    """Accept only names, teams, saved availability. No provider projection feature.

    Fixed baseline: last5 explicit observations; exponential half-life3 observed
    games. No absence-to-zero. Unknown histories receive earlier league roster-
    observation mean, explicitly marked cold start. Water-fill to240, cap48.
    """
    capture=pd.Timestamp(captured_at)
    if capture.tzinfo is None:raise ValueError('Timezone-aware pregame capture required')
    available=[]
    for p in roster:
        if str(p.get('status','')).upper().strip() in {'OUT','O','IR','SUSPENDED','INACTIVE'}:continue
        key=player_key(p['name'],p['team'])
        if key in [a[0] for a in available]:raise ValueError('Ambiguous roster identity')
        available.append((key,p))
    if len(available)<5:raise ValueError('Five available players required')
    prior=[]
    for h in history:
        if h['date']>=game_date or (history_ceiling and h['date']>=history_ceiling):continue
        completed=pd.Timestamp(h['completed_at'])
        if completed.tzinfo is None or completed>=capture:continue
        if not np.isfinite(h['minutes']) or not 0<=h['minutes']<=48:raise ValueError('Invalid historical minutes')
        prior.append(h)
    if not prior:raise ValueError('No verified prior completed-game history')
    # League prior includes explicit DNP observations, never missing-roster zeros.
    league=float(np.mean([h['minutes'] for h in prior]));weights=[];items=[]
    for key,p in available:
        own=[h for h in prior if tuple(h['key'])==key]
        own=sorted(own,key=lambda h:(h['date'],h['completed_at'],h['game_id']))[-5:]
        if own:
            recency=2.**(-np.arange(len(own)-1,-1,-1)/3.);raw=float(np.average([h['minutes'] for h in own],weights=recency))
        else:raw=league
        weights.append(raw);items.append({'key':key,'name':p['name'],'team':p['team'],'raw_minutes':raw,'history_n':len(own),'cold_start':not bool(own),'last_history_date':max((h['date'] for h in own),default=None),'status':p.get('status','unknown')})
    if np.count_nonzero(np.array(weights)>0)<5:raise ValueError('Historical positive-minute support cannot fill five court positions')
    predicted=allocate_minutes(np.array(weights)[None,:])[0]
    for row,value in zip(items,predicted):row['predicted_minutes']=float(value)
    return items
