"""Benchmark FD concentration only; never load actual player/contest results."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from simmah_nba_portfolio_limits import portfolio_limits, validate_portfolio_limits
from simmah_nba_rules import rules_for
from simmah_selector_budget import select_quality_budget, QualityNotCertified, CapConflict


def read_build(path):
    raw = Path(path).read_bytes()
    outer_hash = hashlib.sha256(raw).hexdigest()
    with zipfile.ZipFile(io.BytesIO(raw)) as outer:
        if 'original_build.zip' in outer.namelist():
            manifest = json.loads(outer.read('manifest.json'))
            for name, info in manifest['files'].items():
                if hashlib.sha256(outer.read(name)).hexdigest() != info['sha256']:
                    raise ValueError('Outer checksum mismatch')
            raw = outer.read('original_build.zip')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        manifest = json.loads(z.read('manifest.json'))
        for name, info in manifest['files'].items():
            if hashlib.sha256(z.read(name)).hexdigest() != info['sha256']:
                raise ValueError('Build checksum mismatch: ' + name)
        obj = json.loads(z.read('inputs/player_pool.json'))
        pool = pd.DataFrame(obj['rows'])
        pool.attrs = obj['attrs']
        pool['Player ID'] = pool['Player ID'].astype(str)
        if rules_for(pool)['platform'] != 'FanDuel':
            raise ValueError('This benchmark is for NBA FanDuel only')
        slots = list(rules_for(pool)['slots'])
        candidates = pd.read_csv(io.BytesIO(z.read('candidate_lineups.csv')), dtype=str)
        report = pd.read_csv(io.BytesIO(z.read('candidate_scores.csv')))
        count = len(pd.read_csv(io.BytesIO(z.read('portfolio_at_build.csv'))))
        settings = json.loads(z.read('inputs/settings.json'))
        contest = json.loads(z.read('inputs/contest.json'))
    if len(candidates) != len(report):
        raise ValueError('Candidate/report alignment mismatch')
    for frame in (pool, report):
        if any('actual' in str(c).lower() or str(c).lower() == 'won' for c in frame):
            raise ValueError('Actual-result column in pregame inputs')
    if settings['rank_metric_at_build'] != 'Top 1%':
        raise ValueError('Benchmark requires the saved Top 1% metric')
    rows = report.reset_index(drop=True).copy()
    for slot in slots:
        rows[slot] = candidates[slot].astype(str).to_numpy()
    return pool, slots, rows, count, contest['date'], outer_hash


def run(archives, repeats, output, portfolio_count=None):
    if repeats < 1 or (portfolio_count is not None and portfolio_count < 1):
        raise ValueError('Positive repeat and portfolio counts required')
    records = []
    for archive in archives:
        pool, slots, rows, saved_count, date, digest = read_build(archive)
        count = saved_count if portfolio_count is None else portfolio_count
        limits = portfolio_limits(pool, count=count)
        failed = False
        for repeat in range(repeats):
            if repeat and failed:
                break
            # Alternate execution order so warming cannot always favor one arm.
            for tighten in ((False, True) if repeat % 2 == 0 else (True, False)):
                record = dict(date=date, archive_sha256=digest, repeat=repeat,
                    candidates=len(rows), count=count, saved_count=saved_count, tighten=tighten)
                try:
                    selected = select_quality_budget(rows, slots, count,
                        controls=limits, automatic_max=100., quality_metric='Top 1%',
                        quality_loss=.05, diversify=True, time_limit=15., tighten=tighten)
                    validate_portfolio_limits(selected, slots, limits)
                    record['metadata'] = selected.attrs
                except (QualityNotCertified, CapConflict) as error:
                    failed = True
                    record.update(error_type=type(error).__name__, error=str(error))
                records.append(record)
                Path(output).write_text(json.dumps(records, indent=2, default=str) + '\n')
                print(json.dumps(record, default=str), flush=True)
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('archives', nargs='+')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--output', required=True)
    parser.add_argument('--portfolio-count', type=int,
                        help='Controlled size test; otherwise retain saved portfolio count')
    args = parser.parse_args()
    run(args.archives, args.repeats, args.output, args.portfolio_count)
