"""Run an offline development replay; output is an atomic, aggregate-only JSON."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from simmah_slate_replay import replay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True)
    parser.add_argument('--standings', required=True)
    parser.add_argument('--username', required=True)
    parser.add_argument('--lock-time', required=True, help='ISO timestamp with explicit timezone')
    parser.add_argument('--draws', type=int, default=10000)
    parser.add_argument('--seed', type=int, default=83)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = replay(args.package, args.standings, args.username, args.lock_time,
                    draws=args.draws, seed=args.seed)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=output.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')
    try:
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    print(json.dumps({k: report[k] for k in ('platform', 'replay_matches_entered',
        'entered_roi_pct', 'replay_roi_pct', 'random_roi_median', 'replay_one_sided_mc_p')}))


if __name__ == '__main__':
    main()
