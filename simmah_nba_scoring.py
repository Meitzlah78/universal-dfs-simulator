"""FanDuel NBA scoring verified against the uploaded contest rules, 2026-10-20."""

def score_fanduel(*, points=None, fgm=0, threes=0, ftm=0, rebounds=0,
                  assists=0, steals=0, blocks=0, turnovers=0):
    # Three-pointers already contribute three basketball points. Never add the
    # made-three term to an explicitly supplied total points value.
    scoring = points if points is not None else 2*fgm + threes + ftm
    return scoring + 1.2*rebounds + 1.5*assists + 3*steals + 3*blocks - turnovers


def score_draftkings(*, points=None, fgm=0, threes=0, ftm=0, rebounds=0,
                     assists=0, steals=0, blocks=0, turnovers=0):
    import numpy as np
    scoring = points if points is not None else 2*fgm + threes + ftm
    categories=sum(np.asarray(value)>=10 for value in (scoring,rebounds,assists,steals,blocks))
    return (scoring + .5*threes + 1.25*rebounds + 1.5*assists + 2*steals + 2*blocks
            - .5*turnovers + 1.5*(categories>=2) + 3*(categories>=3))


def score_nba(platform='FanDuel', **stats):
    if platform not in {'FanDuel','DraftKings'}:raise ValueError('Unknown NBA scoring platform')
    return (score_draftkings if platform=='DraftKings' else score_fanduel)(**stats)
