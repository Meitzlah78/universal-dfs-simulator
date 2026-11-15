"""NFL availability snapshots and export checks, independent of Streamlit/network."""
import re
import pandas as pd

NFL_TEAMS=set('ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LV LAC LAR MIA MIN NE NO NYG NYJ PHI PIT SF SEA TB TEN WAS'.split())

class InjuryStatuses(dict):
    """A verified response retains team coverage even when nobody is injured."""
    def __init__(self,*args,covered_teams=(),uncertain_keys=(),**kwargs):
        super().__init__(*args,**kwargs)
        self.covered_teams=set(covered_teams)
        self.uncertain_keys=set(uncertain_keys)


def canonical_status(value):
    if isinstance(value,dict):value=value.get('name') or value.get('type') or value.get('description') or value.get('displayName')
    text=re.sub(r'[^a-z0-9]+',' ',str(value or '').lower()).strip()
    return {'out':'Out','o':'Out','injured reserve':'Out','reserve injured':'Out','ir':'Out',
            'physically unable to perform':'Out','pup':'Out','suspended':'Out','reserve suspended':'Out',
            'doubtful':'Doubtful','d':'Doubtful','questionable':'Questionable','q':'Questionable',
            'day to day':'Questionable','probable':'Questionable','p':'Questionable',
            'active':'Active','healthy':'Active'}.get(text)


def parse_injuries(payload,normalize_name,normalize_team):
    blocks=payload.get('injuries') if isinstance(payload,dict) else None
    if not isinstance(blocks,list) or not blocks:raise ValueError('No verified injury team coverage')
    statuses={};covered=set();uncertain=set()
    for block in blocks:
        if not isinstance(block,dict):raise ValueError('Malformed injury team')
        team_data=block.get('team') or {}
        team=normalize_team(team_data.get('abbreviation') or team_data.get('displayName') or team_data.get('name') or block.get('displayName') or block.get('name'))
        injuries=block.get('injuries')
        if team not in NFL_TEAMS or not isinstance(injuries,list):raise ValueError('Unverified injury team coverage')
        covered.add(team)
        for injury in injuries:
            if not isinstance(injury,dict):raise ValueError('Malformed injury record')
            athlete=injury.get('athlete') or {}
            name=normalize_name(athlete.get('fullName') or athlete.get('displayName') or athlete.get('shortName'))
            if not name:raise ValueError('Injury record missing player')
            status=canonical_status(injury.get('status'))
            if status is None:uncertain.add((name,team))
            else:statuses[(name,team)]=status
    return InjuryStatuses(statuses,covered_teams=covered,uncertain_keys=uncertain)


def reconcile_injuries(frame,incoming,state,normalize_name,normalize_team):
    """Only verified coverage can clear an old designation; failures retain it."""
    result=frame.copy();known=dict(state.get('nfl_injury_name_teams',{}))
    legacy={**state.get('player_injury_statuses',{}),**state.get('display_injury_statuses',{})}
    saved=dict(state.get('nfl_verified_injuries',{}))
    for row in result.to_dict('records'):
        name=str(row['Name']);team=normalize_team(row.get('Team',''));key=(normalize_name(name),team)
        known[name]=team
        old=canonical_status(legacy.get(name)) or canonical_status(row.get('Injury Status'))
        if old and key not in saved:saved[key]=old
    previous={name:legacy.get(name,'Unknown') for name in known}
    verified=isinstance(incoming,InjuryStatuses)
    covered=incoming.covered_teams if verified else set()
    if verified:
        saved={k:v for k,v in saved.items() if k[1] not in covered or k in incoming.uncertain_keys}
        saved.update(incoming)
    by_name=dict(legacy)
    for name,team in known.items():
        key=(normalize_name(name),team)
        by_name[name]=saved.get(key,'Active' if team in covered and key not in incoming.uncertain_keys else 'Unknown') if verified else saved.get(key,by_name.get(name,'Unknown'))
    result['Injury Status']=[by_name[str(n)] for n in result.Name]
    state['nfl_verified_injuries']=saved
    state['nfl_injury_name_teams']=known
    state['player_injury_statuses']=by_name
    state['display_injury_statuses']=dict(by_name)
    return result,{'verified':verified,'changed':verified and any(by_name.get(n)!=previous.get(n) for n in known),'covered_teams':covered,
                   'unverified_slate_teams':{normalize_team(t) for t in result.get('Team',pd.Series(dtype=str))}-covered,
                   'uncertain_slate_players':[str(row['Name']) for row in result.to_dict('records') if verified and (normalize_name(row['Name']),normalize_team(row.get('Team',''))) in incoming.uncertain_keys]}


def out_players(lineups,slots,statuses,normalize_name):
    if not isinstance(lineups,pd.DataFrame) or lineups.empty:return []
    out={normalize_name(n) for n,s in statuses.items() if canonical_status(s)=='Out'}
    found=set()
    for col in slots:
        if col not in lineups:continue
        for value in lineups[col].astype(str):
            name=re.sub(r'\s*\(\d+\)\s*$','',value).strip()
            if normalize_name(name) in out:found.add(name)
    return sorted(found)
