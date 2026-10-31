"""Bounded event-input calibration to pregame implied team scores."""
import math
import numpy as np


def canonical_targets(markets):
    targets = {}
    for team, values in (markets or {}).items():
        key = str(team).upper().strip()
        key = {'WSH':'WAS','JAC':'JAX','LA':'LAR'}.get(key,key)
        try:
            value = float(values[0])
        except (ValueError, TypeError, IndexError):
            raise ValueError('Invalid implied team score')
        if not math.isfinite(value) or not 0 < value <= 60:
            raise ValueError('Invalid implied team score')
        targets[key] = value
    return dict(sorted(targets.items()))


def calibrate_market_inputs(pool, roles, parameters, weather, platform, targets, pilot_n=1024, steps=3):
    """Fit team yardage-efficiency inputs, never rescale fantasy points/outcomes.

    A separate fixed pilot seed is excluded from construction and evaluation.
    Market targets constrain scoring environments; external player projections
    still determine roles and fitted individual opportunity/efficiency inputs.
    """
    if not targets:
        return {}, []
    from simmah_nfl_engine import simulate_stat_lines
    gains = {team:1. for team in targets}
    initial = {}
    for iteration in range(steps + 1):
        _, diagnostic = simulate_stat_lines(pool, roles, np.random.default_rng(830117), pilot_n,
            weather_by_team=weather, projection_inputs=parameters, scoring_platform=platform,
            market_gain=gains, return_diagnostics=True)
        means = {team:float(np.mean(diagnostic[team]['points'])) for team in targets if team in diagnostic}
        if iteration == 0:
            initial = means.copy()
        if iteration == steps:
            break
        for team, mean in means.items():
            gains[team] = float(np.clip(gains[team] * (targets[team]/max(mean,1.))**.35, .65, 1.5))
    report = [{'Team':team, 'Market target':target, 'Before market calibration':initial.get(team),
               'Pilot mean':means.get(team), 'Event efficiency':gains[team],
               'Bound reached':gains[team] <= .65001 or gains[team] >= 1.49999}
              for team,target in targets.items() if team in means]
    return gains, report
