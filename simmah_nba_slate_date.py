"""Resolve NBA dates from explicit slate evidence, never the current day."""
from datetime import date
import json
from pathlib import Path
import re
import pandas as pd


def resolve_slate_date(slate,filename,contest_folder=None):
    evidence=[]
    def add(value,source):
        if value:evidence.append((date.fromisoformat(str(value)).isoformat(),source))
    add(slate.get('date'),'uploaded slate')
    pool=slate['players']
    add(pool.attrs.get('slate_date'),'salary table')
    for column in ('Game Start','GameStart'):
        if column in pool:
            for raw in pool[column].dropna().unique():
                stamp=pd.Timestamp(raw)
                if stamp.tzinfo is None:continue  # Ambiguous clocks do not prove a slate date.
                add(stamp.tz_convert('America/New_York').date().isoformat(),'game start')
    match=re.search(r'NBA-(\d{4}-\d{2}-\d{2})-',str(filename),re.I)
    if match:add(match[1],'original filename')
    folder=Path(contest_folder) if contest_folder is not None else Path(__file__).parent/'data/nba_contests'
    for selected in slate.get('contests',[]):
        cid=str(selected['id'])
        if not re.fullmatch(r'\d+(?:-\d+)?',cid):continue
        path=folder/(cid+'.json')
        if path.exists():
            known=json.loads(path.read_text())
            if str(known['id'])==cid and abs(float(known['entry_fee'])-float(selected['entry_fee']))<1e-9:
                add(known['date'],'saved contest '+cid)
    days={d for d,_ in evidence}
    if len(days)>1:raise ValueError('Conflicting NBA slate dates: '+', '.join(d+' ('+source+')' for d,source in evidence))
    return next(iter(days)) if days else None
