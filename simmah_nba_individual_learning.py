"""Per-player challengers evaluated against frozen, genuinely pregame feed rates."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import numpy as np
from simmah_nba_learning import identities, name_key, ROLE_COLUMNS
from simmah_nba_roles import fit_roles, observations, ROLES


def frozen_snapshot(pool, captured_at):
    """Keep source rates in exported pool attrs; ignore players already started."""
    stamp = datetime.fromisoformat(captured_at)
    if stamp.tzinfo is None:
        raise ValueError('Individual-rate snapshot needs a timezone')
    players = {}
    for _, row in pool.iterrows():
        if str(row.get('Role Rate Source', '')) != 'Individual historical rates':
            continue
        try:
            start = datetime.fromisoformat(str(row['Game Start']).replace('Z', '+00:00'))
            rates = np.asarray([row[c] for c in ROLE_COLUMNS], float)
            if start.tzinfo is None or stamp >= start:
                continue
            if not np.isfinite(rates).all() or (rates < 0).any() or rates.sum() <= 0:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        key = name_key(row['Name'])
        record = {'rates': rates.tolist(), 'game_start': start.isoformat(),
                  'source': 'Individual historical rates'}
        if key in players:
            raise ValueError('Ambiguous player name in individual-rate snapshot')
        players[key] = record
    return {'schema': 1, 'captured_at': stamp.isoformat(), 'players': players}


def validate_individual(games, snapshots, today, minimum_games=4):
    """Each player's fixed challenger must beat their feed on two later periods.

    Missing pregame snapshots never become synthetic position-prior comparisons.
    Fitting ends before the earliest evaluation date. Actual minutes are used
    only to score held-out stat-rate errors, never to forecast a rotation.
    """
    today = str(today)
    if any(g['date'] >= today for g in games):
        raise ValueError('Individual validation includes target-day/future results')
    list(observations(games, today))  # duplicates and corrupt counts fail closed
    records = {}
    for snapshot in snapshots:
        captured = datetime.fromisoformat(snapshot['captured_at'])
        if captured.tzinfo is None:
            raise ValueError('Snapshot timestamp needs a timezone')
        for key, row in snapshot['players'].items():
            start = datetime.fromisoformat(row['game_start'])
            rates = np.asarray(row['rates'], float)
            if (start.tzinfo is None or captured >= start or rates.shape != (5,)
                    or not np.isfinite(rates).all() or (rates < 0).any()
                    or rates.sum() <= 0 or row['source'] != 'Individual historical rates'):
                raise ValueError('Invalid frozen individual-rate snapshot')
            # Use game-local calendar day, consistent with the archive date.
            token = (key, start.date().isoformat())
            if token not in records or captured > records[token][0]:
                records[token] = (captured, rates)
    report = {'status': 'pending', 'as_of': today, 'players': {},
              'scope': 'Per-player stat counts conditional on observed minutes; not ROI',
              'reason': 'Need frozen pregame individual rates and four later player games'}
    eligible_dates = sorted({g['date'] for g in games if any(day == g['date'] for _, day in records)})
    if not eligible_dates:
        return report
    boundary = eligible_dates[0]
    training = [g for g in games if g['date'] < boundary]
    if not training:
        return report
    fitted = fit_roles(training, boundary)
    names, _ = identities(training)
    by_player = {}
    for game in sorted(games, key=lambda g: (g['date'], g['event_id'])):
        if game['date'] < boundary:
            continue
        test_names, _ = identities([game])
        keys = {pid: key for key, pid in test_names.items() if names.get(key) == pid}
        for pid, minutes, actual in observations([game], today):
            key = keys.get(pid)
            frozen = records.get((key, game['date']))
            player = fitted['players'].get(pid)
            if frozen is None or not player or player['minutes'] < 60:
                continue
            new = np.asarray(player['rates'], float)
            by_player.setdefault(key, []).append((game['date'], str(game['event_id']),
                abs(new * minutes - actual), abs(frozen[1] * minutes - actual)))
    approved = {}
    for key, rows in by_player.items():
        if len(rows) < minimum_games or len({r[0] for r in rows}) < 4:
            continue
        split = len(rows) // 2
        selection, confirmation = rows[:split], rows[split:]
        if selection[-1][0] >= confirmation[0][0]:
            continue
        ratios = []
        for period in (selection, confirmation):
            new = np.mean([r[2] for r in period], axis=0)
            old = np.mean([r[3] for r in period], axis=0)
            ratios.append(1 + (new - old) / np.maximum(old, .01))
        mask = (ratios[0] <= .99) & (ratios[1] <= .99)
        report['players'][key] = {'selection_error_ratio': dict(zip(ROLES, ratios[0].tolist())),
            'confirmation_error_ratio': dict(zip(ROLES, ratios[1].tolist())),
            'accepted_roles': [r for r, keep in zip(ROLES, mask) if keep],
            'selection_ids': [r[1] for r in selection], 'confirmation_ids': [r[1] for r in confirmation]}
        if mask.any():
            player = fitted['players'][names[key]]
            approved[key] = {**player, 'enabled_roles': report['players'][key]['accepted_roles']}
    report.update(status='approved' if approved else 'pending' if not report['players'] else 'rejected',
                  training_before=boundary, training_ids=[g['event_id'] for g in training])
    if report['status'] != 'pending':
        report.pop('reason', None)
    if approved:
        report['model'] = {'schema': 1, 'approved': True, 'activation_date': today,
            'training_before': boundary, 'validation_through': max(r[0] for rows in by_player.values() for r in rows),
            'players_by_name': approved, 'validation': report.copy()}
    return report


def apply_individual(pool, slate_day, root):
    out = pool.copy()
    path = Path(root) / 'individual_role_challenger.json'
    out.attrs['nba_individual_learning'] = {'status': 'No validated individual challenger', 'matched_players': 0}
    if not path.exists():
        return out
    envelope = json.loads(path.read_text())
    model = envelope['model']
    digest = hashlib.sha256(json.dumps(model, sort_keys=True).encode()).hexdigest()
    if digest != envelope['sha256']:
        raise ValueError('Individual challenger checksum mismatch')
    if (not model['approved'] or not model['training_before'] <= model['validation_through'] < model['activation_date']):
        raise ValueError('Invalid individual challenger dates')
    if model['activation_date'] > str(slate_day):
        return out
    matched = 0
    for idx, row in out.iterrows():
        if row.get('Role Rate Source') != 'Individual historical rates':
            continue
        player = model['players_by_name'].get(name_key(row['Name']))
        if not player:
            continue
        rates = np.asarray(player['rates'], float)
        enabled = player['enabled_roles']
        if (rates.shape != (5,) or not np.isfinite(rates).all() or (rates < 0).any()
                or not enabled or not set(enabled) <= set(ROLES)):
            raise ValueError('Invalid individual challenger rates')
        for role, column, value in zip(ROLES, ROLE_COLUMNS, rates):
            if role in enabled:
                out.at[idx, column] = value
        out.at[idx, 'Role Rate Source'] = 'Validated individual challenger ' + model['activation_date']
        matched += 1
    out.attrs['nba_individual_learning'] = {'status': 'Validated against frozen individual rates',
        'matched_players': matched, 'activation_date': model['activation_date'],
        'validation_through': model['validation_through']}
    return out
