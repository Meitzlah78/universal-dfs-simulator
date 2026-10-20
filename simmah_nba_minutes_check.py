"""Chronological minutes diagnostics conditional on recorded player participation.

No historical injury/news snapshots are available: this cannot evaluate DNP risk
or pretend to be a complete pregame rotation forecast. Overtime games are omitted
from regulation-minute error metrics.
"""
from collections import defaultdict
from datetime import date
import numpy as np
from simmah_nba_roles import observations


def check_minutes(training, holdout, boundary, before, minimum_history=3):
    training=list(training);holdout=list(holdout)
    if minimum_history < 1:
        raise ValueError('Positive minimum history required')
    if date.fromisoformat(boundary) >= date.fromisoformat(before):
        raise ValueError('Holdout boundary must precede target date')
    ids=[g['event_id'] for g in training+holdout]
    if len(ids)!=len(set(ids)):
        raise ValueError('Training and holdout games must be unique')
    history=defaultdict(list)
    for g in sorted(training,key=lambda g:(g['date'],g['event_id'])):
        for pid, minutes, _ in observations([g],boundary):
            # Overtime changes the regulation budget and must not leak into
            # regulation targets or the regulation-only fitting baseline.
            if max(int(e['period']['number']) for e in g['events'])==4:
                history[pid].append(minutes)
    # Freeze at boundary: later holdout games never update these estimates.
    errors=[];mean_errors=[];covered=0;uncovered=0;ot_games=0
    for g in holdout:
        if g['date'] < boundary:
            raise ValueError('Holdout overlaps training dates')
        rows=list(observations([g],before))
        if max(int(e['period']['number']) for e in g['events'])!=4:
            ot_games+=1
            continue
        for pid, actual, _ in rows:
            past=history[pid]
            if len(past)<minimum_history:
                uncovered+=1
                continue
            estimate=float(np.mean(past[-3:]))
            baseline=float(np.mean(past))
            errors.append(estimate-actual)
            mean_errors.append(baseline-actual)
            covered+=1
    if not errors:
        raise ValueError('No held-out players have sufficient prior minutes history')
    e=np.asarray(errors);base=np.asarray(mean_errors)
    return {'boundary':boundary,'covered_player_games':covered,
            'insufficient_history_player_games':uncovered,'excluded_overtime_games':ot_games,
            'last_three_mae':float(abs(e).mean()),'training_mean_mae':float(abs(base).mean()),
            'last_three_bias':float(e.mean()),'last_three_rmse':float(np.sqrt((e*e).mean())),
            'status':'conditional on participation; no DNP/news or injury redistribution validation'}
