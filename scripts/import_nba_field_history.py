"""Import one completed DK Classic standings export with its own salary file.

Only anonymous aggregate habits are saved. Points, ranks, names, player IDs,
entry IDs, and the position-specific %Drafted side table are never training
features. Run from the repository root; see docs/nba-field-history.md.
"""
import argparse
from collections import Counter
from decimal import Decimal
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import zipfile

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from simmah_nba_import import read_template
from simmah_nba_rosters import validate_lineup
from simmah_nba_rules import rules_for, DK_SLOTS
from simmah_nba_field_history import lineup_features, validate_profile, fee_bucket, game_bucket, game_count


def import_contest(standings, template, contest_id, expected_entries, *, return_lineups=False):
    slate = read_template(template)
    pool = slate['players']
    if slate.get('platform') != 'DraftKings':
        raise ValueError('Only DraftKings NBA Classic history is supported')
    selected = [c for c in slate['contests'] if c['id'] == str(contest_id)]
    if len(selected) != 1:
        raise ValueError('Contest must match its historical salary template')
    if pool['Name'].duplicated().any():
        raise ValueError('Ambiguous historical player names; use an ID-based export')
    names = dict(zip(pool['Name'], range(len(pool))))
    raw = standings
    if zipfile.is_zipfile(io.BytesIO(raw)):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            members = [m for m in z.infolist() if m.filename.lower().endswith('.csv')]
            if len(members) != 1 or members[0].file_size > 100_000_000:
                raise ValueError('One bounded standings CSV required')
            raw = z.read(members[0])  # never extract archive paths
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    if not {'EntryId', 'TimeRemaining', 'Lineup'} <= set(reader.fieldnames or []):
        raise ValueError('Completed DraftKings standings CSV required')
    own = {r[0] for r in slate['entries'] if r[1] == str(contest_id)}
    seen = set(); excluded = set(); lineups = []; unavailable = 0
    rules = rules_for(pool)
    # Slot labels are retained for legality, then discarded for canonical IDs.
    pattern = re.compile(r'(?:^|\s)(PG|SG|SF|PF|UTIL|C|G|F)\s+')
    for row in reader:
        entry_id = row.get('EntryId', '').strip()
        if not entry_id:
            continue  # player-stat side table, never a lineup
        if not entry_id.isdigit() or entry_id in seen:
            raise ValueError('Missing or duplicate standings entry ID')
        seen.add(entry_id)
        if Decimal(row.get('TimeRemaining', '')) != 0:
            raise ValueError('Unfinished contest cannot train opponent history')
        text = row.get('Lineup', '').strip()
        if not text:
            if entry_id in own:
                raise ValueError('User entry lineup unavailable; cannot verify exclusions')
            unavailable += 1
            continue
        matches = list(pattern.finditer(text))
        if len(matches) != len(DK_SLOTS) or matches[0].start() != 0:
            raise ValueError('Incomplete historical lineup')
        slots = {}
        for i, match in enumerate(matches):
            name = text[match.end():matches[i+1].start() if i+1 < len(matches) else len(text)].strip()
            if match[1] in slots or name not in names:
                raise ValueError('Unknown/ambiguous player or duplicate slot in history')
            slots[match[1]] = names[name]
        if set(slots) != set(DK_SLOTS):
            raise ValueError('Historical roster slots differ from DK Classic')
        ids = [slots[s] for s in DK_SLOTS]
        validate_lineup(pool, pool.iloc[ids]['Player ID'].tolist(),
                        salary_cap=rules['salary_cap'], max_from_team=rules['max_from_team'],
                        require_projections=False)
        if entry_id in own:
            excluded.add(entry_id)
        else:
            lineups.append(ids)
    if len(seen) != expected_entries or excluded != own or not lineups:
        raise ValueError('Incomplete field or missing user entries; verify expected entry count')
    ids = np.asarray(lineups, dtype=int)
    features = lineup_features(pool, ids)
    copies = Counter(tuple(sorted(row)) for row in ids.tolist())
    profile = {
        'schema': 1, 'sport': 'NBA', 'platform': 'DraftKings', 'contest_id': str(contest_id),
        'date': slate['date'], 'fee_bucket': fee_bucket(selected[0]['entry_fee']),
        'game_bucket': game_bucket(game_count(pool)), 'games': game_count(pool),
        'source_sha256': hashlib.sha256(standings).hexdigest(),
        'salary_template_sha256': hashlib.sha256(template).hexdigest(),
        'total_entries': len(seen), 'excluded_user_entries': len(excluded),
        'unavailable_lineup_entries': unavailable,
        'opponent_entries': len(ids), 'unique_opponent_rosters': len(copies),
        'duplicate_entry_fraction': 1 - len(copies) / len(ids),
        'largest_roster_copies': max(copies.values()),
        'histograms': {k: {str(i): int(v) for i, v in sorted(Counter(a.tolist()).items())}
                       for k, a in features.items()},
        'limitations': ['One contest; no independent future-contest validation',
                        'Duplicate statistics recorded, not separately calibrated',
                        'No individual player pairing model or ownership targets learned'],
    }
    validate_profile(profile)
    return (profile, pool, ids) if return_lineups else profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--standings', required=True, type=Path)
    parser.add_argument('--template', required=True, type=Path)
    parser.add_argument('--contest', required=True)
    parser.add_argument('--expected-entries', required=True, type=int)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    profile = import_contest(args.standings.read_bytes(), args.template.read_bytes(),
                             args.contest, args.expected_entries)
    # Exclusive create prevents silently replacing a frozen contest profile.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as out:
        out.write(json.dumps(profile, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: v for k, v in profile.items() if k != 'histograms'}, indent=2))


if __name__ == '__main__':
    main()
