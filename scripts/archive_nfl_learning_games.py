"""Refresh complete NFL weeks; retain usable existing archives on feed failures."""
import argparse
from datetime import datetime,timezone
from hashlib import sha256
import io
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
from urllib.request import urlopen
from urllib.error import URLError
from simmah_nfl_learning import atomic_json

FIELDS=set('season season_type week game_id old_game_id game_date home_team away_team posteam defteam play_id drive qtr down ydstogo yardline_100 game_seconds_remaining score_differential play_type yards_gained epa wp wpa passer_player_id passer_player_name receiver_player_id receiver_player_name rusher_player_id rusher_player_name yards_after_catch air_yards complete_pass incomplete_pass interception sack touchdown pass_touchdown rush_touchdown run_location run_gap shotgun no_huddle qb_dropback qb_scramble two_point_attempt extra_point_attempt field_goal_attempt kickoff_attempt punt_attempt total_home_score total_away_score home_score away_score field_goal_result kick_distance kicker_player_id kicker_player_name extra_point_result two_point_conv_result fumble_lost return_touchdown safety blocked_player_id td_team fumble_recovery_1_team'.split())


def complete_weeks(pbp,schedule,season,as_of):
    required={'season','week','game_id','gameday','home_score','away_score','game_type'}
    if not required<=set(schedule):raise ValueError('Schedule missing final-game fields')
    games=schedule.loc[schedule.season.eq(season)&schedule.game_type.eq('REG')].copy()
    games['gameday']=pd.to_datetime(games.gameday,utc=True,errors='coerce')
    cutoff=pd.Timestamp(as_of).tz_convert('UTC').normalize()
    output={}
    for week,rows in games.groupby('week'):
        if rows.game_id.duplicated().any() or rows.game_id.isna().any():raise ValueError('Ambiguous scheduled game identity')
        if not rows.gameday.lt(cutoff).all():continue
        scores=rows[['home_score','away_score']].apply(pd.to_numeric,errors='coerce')
        if scores.isna().any().any():continue
        expected=set(rows.game_id.astype(str))
        archived=pbp.loc[pbp.game_id.astype(str).isin(expected)]
        if set(archived.game_id.astype(str))!=expected:continue
        complete=True
        for _,plays in archived.groupby('game_id'):
            reg=plays.loc[pd.to_numeric(plays.qtr,errors='coerce').between(1,4)]
            if not pd.to_numeric(reg.game_seconds_remaining,errors='coerce').eq(0).any():complete=False;break
        if complete:output[int(week)]=archived.copy()
    return output


def refresh(root,status_path,now=None,get=None):
    now=pd.Timestamp.now(tz='UTC') if now is None else pd.Timestamp(now)
    if now.tzinfo is None:raise ValueError('Timezone-aware archive clock required')
    season=now.year if now.month>=3 else now.year-1
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    def download(url):
        with urlopen(url,timeout=180) as response:return response.read()
    get=get or download
    pbp_url=f'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.csv'
    schedule_url='https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv'
    try:
        responses=[]
        for url in [pbp_url,schedule_url]:
            responses.append(get(url))
        pbp=pd.read_csv(io.BytesIO(responses[0]),usecols=lambda c:c in FIELDS,low_memory=False)
        schedule=pd.read_csv(io.BytesIO(responses[1]),low_memory=False)
        weeks=complete_weeks(pbp,schedule,season,now)
        if not weeks:raise ValueError('No fully completed regular-season weeks verified')
        for week,frame in sorted(weeks.items()):
            output=root/f'{season}_week_{week:02d}.csv.gz'
            # Gzip mtime=0 keeps identical provider data byte-identical across runs.
            frame.sort_values(['game_id','play_id']).to_csv(output,index=False,compression={'method':'gzip','mtime':0})
        status={'status':'fresh completed-game feed','checked_at':now.isoformat(),'season':season,
            'completed_weeks':sorted(weeks),'games':sum(v.game_id.nunique() for v in weeks.values()),
            'sources':[{'url':url,'sha256':sha256(raw).hexdigest()} for url,raw in zip([pbp_url,schedule_url],responses)],
            'verification':'Published final scores plus all scheduled games and regulation-end markers; provider corrections may occur.'}
    except (URLError,TimeoutError,OSError,ValueError,KeyError) as exc:
        paths=list(root.glob('*.csv.gz'))
        if len(paths)<3:raise
        status={'status':'feed unavailable; using existing saved games','checked_at':now.isoformat(),
            'reason':str(exc),'archive_files':len(paths)}
    atomic_json(status_path,status)
    return status


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives',default='data/pbp');parser.add_argument('--status',default='data/nfl_models/feed_status.json')
    args=parser.parse_args();print(json.dumps(refresh(args.archives,args.status),indent=2))

if __name__=='__main__':main()
