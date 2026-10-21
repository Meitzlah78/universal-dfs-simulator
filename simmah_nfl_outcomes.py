"""Separate published contest player scores from anonymous field-model profiles."""
import hashlib
import json
import math
import re
from datetime import date,datetime,timezone
import pandas as pd


def archive_completed_scores(state,frames,profiles,raw_digest,filename,slate_date=None):
    """Retain explicit site FPTS, including zeros; never infer an absent score.

    Uploaded completed standings supply the final-status assertion. Scores are
    not independently verified and are never automatically used to fit a model.
    Source names are retained only in this browser-owned outcome archive.
    """
    if slate_date is not None:slate_date=date.fromisoformat(str(slate_date)).isoformat()
    archive=state.setdefault('nfl_completed_player_results',{})
    added=0;players_saved=0
    for index,frame in enumerate(frames):
        columns={str(c).strip().casefold():c for c in frame.columns}
        if not {'player','fpts'}<=set(columns):continue
        # ingest_frames validates completed-contest shape and site first.
        if not profiles:continue
        formats={profile['format'] for profile in profiles}
        sites={'FanDuel' if fmt.startswith('FD') else 'DraftKings' for fmt in formats}
        if len(sites)!=1:raise ValueError('Mixed scoring platforms cannot share an outcome archive')
        site=next(iter(sites));values={}
        for name,raw in frame[[columns['player'],columns['fpts']]].itertuples(index=False,name=None):
            if pd.isna(name) or not str(name).strip() or pd.isna(raw) or str(raw).strip()=='':continue
            label=str(name).strip()
            try:points=float(str(raw).replace(',',''))
            except ValueError:raise ValueError('Malformed published fantasy score')
            if not math.isfinite(points):raise ValueError('Nonfinite published fantasy score')
            if label in values and abs(values[label]-points)>1e-8:raise ValueError('Conflicting published fantasy scores for '+label)
            values[label]=points
        if not values:continue
        rows=[]
        for label,points in sorted(values.items()):
            match=re.search(r'\((\d+(?:-\d+)?)\)\s*$',label)
            rows.append({'Player':label,'Player ID':match.group(1) if match else None,'Actual Points':points})
        identity=hashlib.sha256(json.dumps([site,slate_date,sorted(formats),rows],sort_keys=True,allow_nan=False).encode()).hexdigest()
        if identity in archive:continue
        archive[identity]={'schema':1,'platform':site,'formats':sorted(formats),'slate_date':slate_date,
            'source_file':str(filename),'source_sha256':raw_digest,'players':rows,
            'imported_at':datetime.now(timezone.utc).isoformat(),
            'status':'User-uploaded completed standings; final status not independently verified',
            'usage':'Validation archive only; no automatic projection or parameter updates',
            'missing_policy':'Unlisted or missing scores are unknown, never zero',
            'coverage':'Only players explicitly listed in this file; not guaranteed full-slate coverage'}
        added+=1;players_saved+=len(rows)
    return {'snapshots_added':added,'player_scores_added':players_saved}


def load_seed_results(state,root):
    """Restore checked-in published scores without fitting or changing projections."""
    from pathlib import Path
    archive=state.setdefault('nfl_completed_player_results',{})
    for path in sorted(Path(root).glob('*.json')):
        payload=json.loads(path.read_text())
        if payload.get('schema')!=1 or not isinstance(payload.get('snapshots'),dict):
            raise ValueError('Invalid completed-player results seed')
        for identity,record in payload['snapshots'].items():
            if record.get('schema')!=1 or record.get('platform') not in {'DraftKings','FanDuel'} or not isinstance(record.get('players'),list):
                raise ValueError('Invalid player-score snapshot')
            for player in record['players']:
                if not player.get('Player') or not math.isfinite(float(player['Actual Points'])):
                    raise ValueError('Invalid published player score')
            archive.setdefault(identity,record)
    return archive
