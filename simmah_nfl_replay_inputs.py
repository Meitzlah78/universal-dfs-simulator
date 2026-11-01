"""Pair immutable private pregame snapshots with explicit final NFL raw stats.

No fantasy-score inversion, fuzzy player matching or missing-value zero fill.
The provider/user asserts FINAL; provenance is retained, not independently proven.
"""
from hashlib import sha256
import json
from pathlib import Path
import numpy as np
import pandas as pd
from simmah_nfl_engine import STAT_KEYS
from simmah_nfl_learning import atomic_json,digest


def assemble_replays(snapshots,actuals,*,source_sha256):
    required={'Game ID','Kickoff','Team','Opponent','Name','Status',*STAT_KEYS}
    if not required<=set(actuals):raise ValueError('Missing final raw-stat columns: '+', '.join(sorted(required-set(actuals))))
    if not isinstance(source_sha256,str) or len(source_sha256)!=64 or any(c not in '0123456789abcdef' for c in source_sha256):
        raise ValueError('Final-stat source SHA-256 required')
    frame=actuals.copy()
    if frame[list(required)].isna().any().any():raise ValueError('Missing final raw values, including identity fields')
    if not frame.Status.astype(str).str.upper().eq('FINAL').all():raise ValueError('All actual rows must explicitly be FINAL')
    for column in ['Game ID','Team','Opponent','Name']:
        frame[column]=frame[column].astype(str).str.strip()
        if frame[column].eq('').any():raise ValueError('Empty final identity: '+column)
    if frame.duplicated(['Game ID','Team','Name']).any():raise ValueError('Duplicate player/game raw actuals')
    def clock(value):
        stamp=pd.Timestamp(value)
        if pd.isna(stamp) or stamp.tzinfo is None:raise ValueError('Actual kickoff must be timezone-aware')
        return stamp.tz_convert('UTC')
    frame['Kickoff']=frame.Kickoff.map(clock)
    for key in STAT_KEYS:
        frame[key]=pd.to_numeric(frame[key],errors='coerce')
        if not np.isfinite(frame[key]).all():raise ValueError('Missing/nonfinite actual stat: '+key)
        if key not in {'passing_yards','rushing_yards','receiving_yards','yards_allowed'}:
            if frame[key].lt(0).any() or not np.equal(frame[key],np.floor(frame[key])).all():
                raise ValueError('Negative/fractional event count: '+key)
    games={}
    for gid,rows in frame.groupby('Game ID'):
        teams=set(rows.Team)|set(rows.Opponent)
        if len(teams)!=2 or rows.Kickoff.nunique()!=1:raise ValueError('Conflicting final game identity: '+str(gid))
        key=(rows.Kickoff.iloc[0],tuple(sorted(teams)))
        if key in games:raise ValueError('Conflicting game IDs for one kickoff/matchup')
        games[key]=(str(gid),rows)
    # Prefer the last pre-tipoff snapshot independently for each site/context.
    latest={};reports=[]
    for snapshot in snapshots:
        kickoff=clock(snapshot['kickoff']);frozen=clock(snapshot['frozen_at'])
        if frozen>=kickoff:raise ValueError('Postgame input labeled pregame')
        teams=tuple(sorted({str(row['Team']) for row in snapshot['pool']}))
        if len(teams)!=2:raise ValueError('Pregame snapshot needs both teams')
        context=(kickoff,teams,snapshot['platform'])
        previous=latest.get(context)
        if previous is None or frozen>clock(previous['frozen_at']):latest[context]=snapshot
    cases=[]
    for (kickoff,teams,platform),snapshot in sorted(latest.items()):
        match=games.get((kickoff,teams))
        if match is None:
            reports.append({'game':snapshot['game_id'],'platform':platform,'status':'no exact final game match'});continue
        gid,rows=match;raw={};missing=[]
        for player in snapshot['pool']:
            role=snapshot['roles'].get(player['Name'],{})
            pid=str(role.get('player_id',''))
            eligible=rows.loc[rows.Team.eq(str(player['Team']))&rows.Opponent.eq(str(player['Opponent']))]
            # Use stable provider IDs when both sides carry one. Exact name/team
            # is allowed only when identity evidence is absent on one side.
            if pid and 'Player ID' in eligible and eligible['Player ID'].notna().any():
                selected=eligible.loc[eligible['Player ID'].astype(str).eq(pid)]
            else:selected=eligible.loc[eligible.Name.eq(str(player['Name']))]
            if len(selected)!=1:
                missing.append(str(player['Name']));continue
            raw[str(player['Name'])]={key:float(selected.iloc[0][key]) for key in STAT_KEYS}
        if missing:
            reports.append({'game':gid,'platform':platform,'status':'incomplete exact player coverage','missing_players':missing});continue
        case=dict(snapshot,game_id=gid,actual_stats=raw,status='explicit final raw actuals paired with pregame inputs',
            actual_source_sha256=source_sha256,pregame_snapshot_sha256=digest(snapshot),
            actual_status_provenance='FINAL assertion from supplied raw-stat source; not independently verified')
        cases.append(case);reports.append({'game':gid,'platform':platform,'status':'ready','players':len(raw)})
    return cases,reports


def read_snapshots(root):
    result=[]
    for path in sorted(Path(root).rglob('*.json')):
        payload=json.loads(path.read_text())
        if isinstance(payload,dict) and 'pregame_replay_inputs' in payload:
            result.extend(payload['pregame_replay_inputs'])
        elif isinstance(payload,dict) and {'pool','kickoff','frozen_at','projection_inputs'}<=set(payload):
            result.append(payload)
    return result


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshots',required=True,help='Private replay_inputs or prepared-manifest directory')
    parser.add_argument('--actuals',required=True,help='Complete canonical FINAL raw-stat CSV, not contest fantasy scores')
    parser.add_argument('--output',required=True,help='Private replay-case output directory')
    args=parser.parse_args();raw=Path(args.actuals).read_bytes()
    frame=pd.read_csv(args.actuals,dtype={'Player ID':str,'Game ID':str})
    cases,report=assemble_replays(read_snapshots(args.snapshots),frame,source_sha256=sha256(raw).hexdigest())
    out=Path(args.output)
    for case in cases:atomic_json(out/(digest(case)+'.json'),case)
    # Keep report outside the case directory consumed by the learner.
    atomic_json(out.with_name(out.name+'-assembly-report.json'),{'ready':len(cases),'games':report})
    print(json.dumps({'ready_contexts':len(cases),'unready_contexts':sum(r['status']!='ready' for r in report)},indent=2))

if __name__=='__main__':main()
