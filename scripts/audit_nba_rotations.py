"""Usage: python scripts/audit_nba_rotations.py archive.tar.xz --before YYYY-MM-DD --output audit.json"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_nba_rotations import audit_rows,read_archive


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive',type=Path);p.add_argument('--before',required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    result=audit_rows(read_archive(args.archive),args.before)
    result['archive_sha256']=hashlib.sha256(args.archive.read_bytes()).hexdigest()
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(f"{result['accepted_games']}/{result['source_games']} games passed structural checks; box-score audit still required")


if __name__=='__main__':main()
