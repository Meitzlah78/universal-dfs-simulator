"""Run the live NBA build regressions without fetching external provider data."""
import argparse
import os
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tests'))

# These exercise offline research/corpus tooling, not the live build route.
# Exact DP calibration has its own input-archive-calibration workflow.
RESEARCH_TESTS={
    'test_nba_canonical_dp',
    'test_nba_history_check',
    'test_nba_minutes_pilot',
    'test_nba_rotation_season_sample',
}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full-scale',action='store_true',help='Replay 10,000 scenarios per phase, 5,000 candidates and 10,000 requested field-support rosters')
    args=parser.parse_args()
    if args.full_scale:
        os.environ['SIMMAH_NBA_FULL_SCALE']='1'
        names=['test_nba_build_contract.BuildContractTests.test_full_scale_build_to_export']
    else:
        names=[p.stem for p in sorted((ROOT/'tests').glob('test_nba*.py')) if p.stem not in RESEARCH_TESTS]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names))
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())
