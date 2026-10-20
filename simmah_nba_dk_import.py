"""DraftKings NBA eight-slot entries with embedded salary table and dated games."""
import csv,io,re
from decimal import Decimal
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
from simmah_nba_projections import team_key
from simmah_nba_rules import DK_SLOTS


def player_id(value):
    value=str(value).strip()
    match=re.search(r'\((\d+)\)$',value)
    result=match[1] if match else value
    if not result.isdigit():raise ValueError('Numeric DraftKings player ID required')
    return result


def read_draftkings(data):
    rows=list(csv.reader(io.StringIO(data.decode('utf-8-sig'))))
    if not rows or tuple(rows[0][:4])!=('Entry ID','Contest Name','Contest ID','Entry Fee') or tuple(rows[0][4:12])!=DK_SLOTS:
        raise ValueError('Expected DraftKings NBA Classic eight-slot entries CSV')
    entries=[]
    for r in rows[1:]:
        if len(r)>=12 and r[0].isdigit() and r[2].isdigit():
            entries.append([r[0],r[2],r[1],r[3].replace('$','').replace(',',''),
                            *[player_id(v) if v.strip() else '' for v in r[4:12]]])
    if not entries or len({r[0] for r in entries})!=len(entries):raise ValueError('NBA entry IDs must be unique')
    start=next((i for i,r in enumerate(rows) if {'Name','ID','Salary','Game Info','TeamAbbrev','Roster Position'}<=set(r)),None)
    if start is None:raise ValueError('DraftKings NBA salary table is missing')
    header=rows[start];players=[];days=set()
    def cell(r,k):
        index=header.index(k)
        return r[index].strip() if index<len(r) else ''
    for r in rows[start+1:]:
        raw=cell(r,'ID')
        if not raw:continue
        pid=player_id(raw);pos=cell(r,'Position');name=cell(r,'Name');salary=Decimal(cell(r,'Salary'))
        if not name or salary<=0 or salary!=int(salary) or not set(pos.split('/'))<={'PG','SG','SF','PF','C'}:
            raise ValueError('Invalid DraftKings NBA salary player')
        game=cell(r,'Game Info')
        match=re.fullmatch(r'(\w+)@(\w+)\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2}[AP]M)\s+ET',game)
        if not match:raise ValueError('Dated NBA game start required in DraftKings Game Info')
        away,home=map(team_key,match.group(1,2));team=team_key(cell(r,'TeamAbbrev'))
        if team not in {away,home}:raise ValueError('NBA salary team differs from game')
        stamp=datetime.strptime(match[3]+' '+match[4],'%m/%d/%Y %I:%M%p').replace(tzinfo=ZoneInfo('America/New_York'))
        days.add(stamp.date().isoformat())
        players.append({'Player ID':pid,'Name':name,'Position':pos,'Salary':int(salary),'Team':team,
                        'Opponent':home if team==away else away,'Game':away+'@'+home,
                        'Game Start':stamp.isoformat(),'Injury Status':'Active','Injury Details':'',
                        'Historical FPPG':float(cell(r,'AvgPointsPerGame') or 0),'Projection':None})
    pool=pd.DataFrame(players)
    if pool.empty or pool['Player ID'].duplicated().any() or len(days)!=1:raise ValueError('Unique players and a single NBA slate date required')
    known=set(pool['Player ID'])
    if any(v and v not in known for r in entries for v in r[4:12]):raise ValueError('Entry player is not in this NBA salary slate')
    pool.attrs['platform']='DraftKings';pool.attrs['slate_date']=next(iter(days))
    contests=[]
    for cid in dict.fromkeys(r[1] for r in entries):
        owned=[r for r in entries if r[1]==cid]
        if len({(r[2],r[3]) for r in owned})!=1:raise ValueError('Conflicting NBA contest metadata')
        contests.append({'id':cid,'name':owned[0][2],'entry_fee':float(Decimal(owned[0][3])),'owned_entries':len(owned)})
    return {'players':pool,'entries':entries,'contests':contests,'slots':DK_SLOTS,'platform':'DraftKings','date':next(iter(days))}
