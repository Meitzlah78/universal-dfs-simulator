"""User-entered pregame market lines and bounded field-popularity adjustments."""
import math
import numpy as np
from simmah_weather import team_key


def implied_scores(total, home_spread):
    """A negative home spread means the home team is favored."""
    try:
        total, home_spread = float(total), float(home_spread)
    except (TypeError, ValueError):
        return None
    if not all(map(math.isfinite, (total, home_spread))) or not 0 < total <= 100 or abs(home_spread) >= total:
        return None
    return (total + home_spread) / 2, (total - home_spread) / 2


def field_market_factors(pool, markets):
    """Experimental heuristic, NOT calibrated ownership or player projections.

    Imported ownership remains authoritative. Missing lines are neutral. Bounds
    prevent an uncalibrated market signal from dominating the field builder.
    """
    factors = np.ones(len(pool), dtype=float)
    if 'Team' not in pool:
        return factors
    for i, row in enumerate(pool.to_dict('records')):
        market = markets.get(team_key(row.get('Team')))
        if not market:
            continue
        points, opponent_points = market
        if not all(math.isfinite(v) for v in (points, opponent_points)):
            continue
        pos = str(row.get('Position', '')).upper()
        signal = ((22 - opponent_points) * .012 + (points - opponent_points) * .004
                  if pos in {'DST', 'D', 'DEF'} else (points - 22) * .012)
        factors[i] = np.clip(1 + signal, .85, 1.15)
    return factors
