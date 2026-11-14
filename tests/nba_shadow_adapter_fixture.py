"""Synthetic canonical-ID evidence, never real certification or validation data."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path

GAME='0022600099';TEAM='1610612749'


def fixture():
    ids=[str(1001+i) for i in range(8)]
    roster={'kind':'team_game_roster_v1','id_namespace':'nba','game_id':GAME,'team_id':TEAM,
        'season_id':'2026-27','scheduled_tipoff':'2026-11-14T23:00:00Z','complete_roster':True,
        'member_player_ids':ids,'players':[{'player_id':pid,'game_id':GAME,'team_id':TEAM,
            'display_name':'Identical names are irrelevant','eligibility':'eligible',
            'status_observed_at':'2026-11-14T17:55:00Z','role_context':'normal',
            'role_context_observed_at':'2026-11-14T17:55:00Z'} for pid in ids]}
    rows=[]
    for day in range(1,13):
        for i,pid in enumerate(ids):
            rows.append({'game_id':f'002260{day:04}','team_id':TEAM,'player_id':pid,
                'season_id':'2026-27','season_type':'regular',
                'game_start_time':f'2026-11-{day:02}T20:00:00Z','game_end_time':f'2026-11-{day:02}T23:00:00Z',
                'regulation_only':True,'participation':'played','minutes':30.,'started':i<5,
                'role_context':'normal','role_context_observed_at':f'2026-11-{day:02}T19:00:00Z'})
    return roster,{'kind':'regulation_history_v1','id_namespace':'nba','records':rows}


def capture(roster=None,history=None):
    r,h=fixture();roster=r if roster is None else roster;history=h if history is None else history
    receipts={};payloads={}
    for source,payload in [('fixture://nba-roster/v1',roster),('fixture://nba-history/v1',history)]:
        raw=json.dumps(payload,sort_keys=True).encode();digest=hashlib.sha256(raw).hexdigest()
        receipts[digest]={'sha256':digest,'source':source,'observed_at':'2026-11-14T17:58:00Z'}
        payloads[digest]=deepcopy(payload)
    hashes=list(receipts)
    request={'game_id':roster['game_id'],'team_id':roster['team_id'],'roster_sha256':hashes[0],'history_sha256':hashes[1]}
    c={'mode':'shadow','capture_id':'synthetic_adapter_case','frozen_at':'2026-11-14T18:00:00Z',
        'receipts':list(receipts.values()),'adapter_requests':[request],'warnings':[],
        'model_source_hashes':{name:hashlib.sha256((Path(__file__).parents[1]/name).read_bytes()).hexdigest()
            for name in ('simmah_nba_shadow_worker.py','simmah_nba_shadow_adapters.py')}}
    return c,request,receipts,payloads


def persist(root,c,payloads):
    root=Path(root)
    for digest,payload in payloads.items():
        raw=json.dumps(payload,sort_keys=True).encode()
        assert hashlib.sha256(raw).hexdigest()==digest
        (root/(digest+'.response.gz')).write_bytes(gzip.compress(raw))
    path=root/(c['capture_id']+'.capture.json');path.write_text(json.dumps(c))
    return path
