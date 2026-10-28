"""NBA market extraction and experimental event-level scoring calibration."""
from dataclasses import replace
import numpy as np
from simmah_nba_engine import simulate_game
from simmah_nba_projections import team_key


def implied_scores(total, home_spread):
    total=float(total);home_spread=float(home_spread)
    if not np.isfinite([total,home_spread]).all() or not 100<total<400 or abs(home_spread)>=total:
        raise ValueError('Invalid NBA total or spread')
    return (total-home_spread)/2,(total+home_spread)/2


def extract_markets(pool):
    """Require consistent two-sided RotoWire lines for uploaded matchups."""
    if not {'Game Total','Team Implied Points'}<=set(pool.columns):return []
    pairs={tuple(sorted((team_key(r.Team),team_key(r.Opponent)))) for r in pool.itertuples()}
    output=[]
    for pair in sorted(pairs):
        team_values=[];totals=[]
        for team in pair:
            group=pool[pool['Team'].map(team_key)==team]
            ts=group['Game Total'].dropna().astype(float).unique()
            pts=group['Team Implied Points'].dropna().astype(float).unique()
            if len(ts)!=1 or len(pts)!=1:break
            totals.append(float(ts[0]));team_values.append(float(pts[0]))
        if len(team_values)!=2:continue
        if not np.isfinite(totals+team_values).all() or abs(totals[0]-totals[1])>.05 or abs(sum(team_values)-totals[0])>.1:
            continue
        # Spread is relative to team[0], independent of a home/away label.
        spread=team_values[1]-team_values[0]
        implied_scores(totals[0],spread)
        output.append({'teams':pair,'total':totals[0],'team_0_spread':spread,
                       'implied_points':tuple(team_values),'source':'RotoWire sportsbook odds'})
    return output


def simulate_market_game(rotations,profiles,rates,targets,seed,pilot_n=1024,iterations=4,overtime_rotations=None,platform='FanDuel',*,calibration_only=False):
    """Adjust shooting event probabilities, never multiply fantasy-score output.

    Markets specify the expected scoring environment; they are not guaranteed
    outcomes. Fixed pilot seed keeps fitting deterministic; final evaluation uses
    another seed. This experimental mapping does not infer pace from total alone.
    """
    targets=np.asarray(targets,float)
    if targets.shape!=(2,) or not np.isfinite(targets).all() or (targets<=40).any() or (targets>=200).any():
        raise ValueError('Two valid NBA team implied scores required')
    if pilot_n<1 or iterations<1:raise ValueError('Positive calibration budget required')
    fitted=list(rates);pilot=np.asarray(rotations)[:pilot_n];baseline=None
    def run(rotation,models,run_seed):
        if overtime_rotations is None:return simulate_game(rotation,profiles,models,run_seed,platform=platform)
        return simulate_game(rotation,profiles,models,run_seed,overtime_rotations=np.asarray(overtime_rotations)[:len(rotation)],platform=platform)
    for _ in range(iterations):
        result=run(pilot,fitted,seed+104729)
        means=result['team_points'].mean(axis=0)
        if baseline is None:baseline=means.tolist()
        if (means<=0).any():raise ValueError('Cannot calibrate a zero-scoring event model')
        for t in range(2):
            factor=np.clip(targets[t]/means[t],.8,1.2)
            fitted[t]=replace(fitted[t],make_two=float(np.clip(fitted[t].make_two*factor,.15,.85)),
                              make_three=float(np.clip(fitted[t].make_three*factor,.1,.75)))
    if calibration_only:
        # Pregame preparation needs fitted parameters, not another pilot game.
        # Every fitting iteration and random seed above remains unchanged.
        return {'calibrated_rates':tuple(fitted),
                'market_calibration':{'baseline_pilot_means':baseline}}
    result=run(rotations,fitted,seed)
    means=result['team_points'].mean(axis=0)
    result['calibrated_rates']=tuple(fitted)
    result['market_calibration']={'targets':targets.tolist(),'baseline_pilot_means':baseline,
         'evaluation_means':means.tolist(),'residual':(means-targets).tolist(),
         'within_four_points':bool((abs(means-targets)<=4).all()),
         'status':'experimental event-level market calibration; not validated for live builds'}
    return result
