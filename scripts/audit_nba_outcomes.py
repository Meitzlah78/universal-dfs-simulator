"""Audit one frozen NBA build against completed archived box scores."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from simmah_nba_outcome_audit import audit_package, archived_games, ARCHIVE

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--archive', type=Path, default=ARCHIVE)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit_package(args.package.read_bytes(), archived_games(args.archive))
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}, indent=2))
