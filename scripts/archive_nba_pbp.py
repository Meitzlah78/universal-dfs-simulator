"""Archive completed NBA games; retry a rolling seven-day window."""
import argparse
from datetime import date, datetime, timedelta
import gzip
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_nba_history import completed_games, download_game


def archive(root, today, lookback=7, schedule=completed_games, download=download_game):
    root=Path(root)
    failures=[];saved=0;existing=0
    for age in range(lookback,0,-1):
        day=(today-timedelta(days=age)).isoformat()
        try:
            ids=schedule(day,today.isoformat())
        except Exception as exc:
            failures.append({'date':day,'reason':str(exc)});continue
        for eid in ids:
            target=root/day/(str(eid)+'.json.gz')
            if target.exists():
                try:
                    with gzip.open(target,'rt') as stream: cached=json.load(stream)
                    if cached['event_id']!=str(eid) or cached['date']!=day or not cached['events']:
                        raise ValueError('Invalid cached game')
                    existing+=1;continue
                except (ValueError,KeyError,OSError,EOFError):pass
            try:
                game=download(eid,today.isoformat())
                if game['date']!=day:raise ValueError('Game date does not match requested schedule')
                target.parent.mkdir(parents=True,exist_ok=True)
                temporary=target.with_suffix('.tmp')
                temporary.write_bytes(gzip.compress(json.dumps(game,separators=(',',':')).encode(),mtime=0))
                temporary.replace(target);saved+=1
            except Exception as exc:
                failures.append({'date':day,'event_id':str(eid),'reason':str(exc)})
    report={'checked_at':datetime.now(ZoneInfo('America/New_York')).isoformat(),
            'through_date':(today-timedelta(days=1)).isoformat(),'lookback_days':lookback,
            'downloaded':saved,'already_archived':existing,'failures':failures}
    root.mkdir(parents=True,exist_ok=True)
    (root/'latest_status.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def run_nightly(root, today, schedule=completed_games, download=download_game):
    """Backfill from October 1 until complete, then maintain a retry window."""
    root=Path(root)
    season_start=date(today.year if today.month>=10 else today.year-1,10,1)
    marker=root/('backfill_'+season_start.isoformat()+'.json')
    backfill=not marker.exists()
    lookback=max(0,(today-season_start).days) if backfill else 7
    report=archive(root,today,lookback=lookback,schedule=schedule,download=download)
    if backfill and not report['failures']:
        marker.write_text(json.dumps({'from_date':season_start.isoformat(),
            'through_date':report['through_date'],'completed_at':report['checked_at']},indent=2)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',default='data/nba_pbp')
    args=parser.parse_args()
    report=run_nightly(args.root,datetime.now(ZoneInfo('America/New_York')).date())
    print(json.dumps(report,indent=2))
    raise SystemExit(bool(report['failures']))
