"""Offline deterministic team-covering sample of a streamed NBA event archive."""
import argparse
import csv
import hashlib
import io
import json
import sys
import tarfile
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_nba_rotations import audit_rows

def archive_rows(path):
    """Read bounded CSV members without extracting paths or loading a season."""
    with tarfile.open(path,'r:xz') as archive:
        members=[m for m in archive.getmembers() if m.isfile() and m.name.endswith('.csv')]
        if len(members)!=1 or members[0].size>500_000_000:
            raise ValueError('Expected one bounded CSV')
        with archive.extractfile(members[0]) as stream:
            yield from csv.DictReader(io.TextIOWrapper(stream,encoding='utf-8-sig'))

def select_sample(games):
    """Select before outcomes: one SHA256-lowest game ID for each team."""
    teams=set().union(*(g['teams'] for g in games.values()))
    return {min((gid for gid,g in games.items() if team in g['teams']),
        key=lambda gid:(hashlib.sha256(gid.encode()).hexdigest(),gid)) for team in teams}

def sample_archive(path,before):
    cutoff=date.fromisoformat(before);games={}
    for row in archive_rows(path):
        day=date.fromisoformat(row['timeActual'][:10])
        if day>=cutoff:continue
        game=games.setdefault(row['gameId'],{'date':day.isoformat(),'teams':set()})
        if row.get('teamId') not in ('','0','0.0',None):
            game['teams'].add(row['teamId'])
    chosen=select_sample(games)
    rows=[r for r in archive_rows(path) if r['gameId'] in chosen]
    result=audit_rows(rows,before)
    teams=set().union(*(g['teams'] for g in games.values()))
    result['sampling']={'method':'Union of SHA256-lowest game ID for each team; selected before minute reconciliation',
        'archive_games_before_cutoff':len(games),'archive_teams':len(teams),
        'selected_game_ids':sorted(chosen),'selected_games':len(chosen),
        'date_range':[min(g['date'] for g in games.values()),max(g['date'] for g in games.values())] if games else []}
    with open(path,'rb') as stream:
        digest=hashlib.file_digest(stream,'sha256').hexdigest()
    result['archive_sha256']=digest
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path);parser.add_argument('--before',required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=sample_archive(args.archive,args.before)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(f"{result['accepted_games']}/{result['sampling']['selected_games']} sampled games pass structural checks; box-score audit required")
if __name__=='__main__':main()
