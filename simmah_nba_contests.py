"""Validated NBA contest metadata from explicitly supplied contest information."""
import json,re
from pathlib import Path
import numpy as np


def payout_vector(contest):
    size=contest['capacity']
    if not isinstance(size,int) or not 1<=size<=1000000:raise ValueError('Invalid NBA contest capacity')
    result=np.zeros(size);last=0
    for tier in contest['payout_tiers']:
        first,end,prize=tier['first'],tier['last'],tier['prize']
        if not isinstance(first,int) or not isinstance(end,int) or first!=last+1 or not first<=end<=size:
            raise ValueError('NBA payout tiers must be contiguous and within contest capacity')
        if not np.isfinite(prize) or prize<=0:raise ValueError('Positive NBA payout required')
        result[first-1:end]=prize;last=end
    if not last or (np.diff(result)>0).any() or abs(result.sum()-contest['prize_pool'])>.01:
        raise ValueError('NBA payout schedule does not match prize pool')
    return result


def saved_contest(contest_id,day,entry_fee):
    if not re.fullmatch(r'\d+-\d+',str(contest_id)):return None
    path=Path(__file__).parent/'data'/'nba_contests'/(str(contest_id)+'.json')
    if not path.exists():return None
    contest=json.loads(path.read_text())
    if contest['id']!=str(contest_id) or contest['date']!=day or abs(contest['entry_fee']-entry_fee)>1e-9:
        raise ValueError('Saved NBA contest differs from uploaded date or entry fee')
    payout_vector(contest)
    return contest
