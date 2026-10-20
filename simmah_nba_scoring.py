"""FanDuel NBA scoring verified against the uploaded contest rules, 2026-10-20."""

def score_fanduel(*, points=None, fgm=0, threes=0, ftm=0, rebounds=0,
                  assists=0, steals=0, blocks=0, turnovers=0):
    # Three-pointers already contribute three basketball points. Never add the
    # made-three term to an explicitly supplied total points value.
    scoring = points if points is not None else 2*fgm + threes + ftm
    return scoring + 1.2*rebounds + 1.5*assists + 3*steals + 3*blocks - turnovers
