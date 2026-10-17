"""Legal tournament baseline for DK Classic opponent proposals.

A QB plus one WR/TE is an explicit modeling assumption, not a learned stack
frequency. It is independent of the user's selected candidate stack rules.
"""
import numpy as np


def classic_tournament_mask(picks, teams, positions, max_from_team=8):
    picks=np.asarray(picks,dtype=int)
    teams=np.asarray(teams,dtype=str)
    positions=np.asarray(positions,dtype=str)
    if picks.ndim!=2 or picks.shape[1]!=9:
        raise ValueError('Classic fields require nine roster slots')
    unique=np.all(np.diff(np.sort(picks,axis=1),axis=1)!=0,axis=1)
    roster_teams=teams[picks]
    # DK limits a lineup to eight players from one team.
    team_counts=(roster_teams[:,:,None]==roster_teams[:,None,:]).sum(axis=2)
    legal_teams=team_counts.max(axis=1)<=max_from_team
    skills=picks[:,1:8]
    pass_catcher=np.array([bool(set(p.split('/')) & {'WR','TE'}) for p in positions],dtype=bool)
    stacked=((teams[skills]==teams[picks[:,0],None]) & pass_catcher[skills]).any(axis=1)
    return unique & legal_teams & stacked
