"""Regenerate native exports from captured inputs and audit without uploading."""
import argparse
import ast
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
from simmah_export_audit import verify_entry_export
from simmah_exports import build_fanduel_entry_export
from simmah_portfolio_selection import select_portfolio
from simmah_slate_workspaces import decode


def audit(path):
    with zipfile.ZipFile(path) as z:
        manifest=json.loads(z.read('manifest.json'))
        for name,item in manifest['files'].items():
            raw=z.read(name)
            if len(raw)!=item['bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:
                raise ValueError('Package integrity failed')
        if z.read('implementation/simmah_portfolio_selection.py')!=Path('simmah_portfolio_selection.py').read_bytes():
            raise ValueError('Selector differs from captured implementation')
        original=z.read('inputs/original_active_slate.csv')
        contest=json.loads(z.read('inputs/contest.json'))
        state=dict(json.loads(z.read('solver/runtime_state.json'))['value'])
        results=pd.read_csv(z.open('scored_lineups.csv'))
        pool=pd.read_csv(z.open('player_pool.csv'))
    dk=manifest['platform']=='DraftKings'
    slots=['Captain','Flex1','Flex2','Flex3','Flex4','Flex5'] if dk else ['MVP','FLEX1','FLEX2','FLEX3','FLEX4','FLEX5']
    control_key='control_values' if dk else 'fd_player_controls_Single Game'
    controls=decode(state[control_key]).set_index('Name').to_dict('index')
    diversity=state['portfolio_exposure_diversity_DraftKings_Showdown_v1' if dk else 'portfolio_exposure_diversity_FanDuel_Single Game_v1']
    portfolio=select_portfolio(results,slots,contest['your_entries'],'Top1',controls=controls,diversity=diversity)
    rows=list(csv.reader(io.StringIO(original.decode('utf-8-sig'))))
    offset=11
    header_row=next(i for i,r in enumerate(rows) if len(r)>offset and r[offset] in ('Position','Player ID + Player Name'))
    table_header=rows[header_row][offset:]
    metadata={};mapping={}
    for row in rows[header_row+1:]:
        data=dict(zip(table_header,row[offset:]))
        ident=data.get('ID' if dk else 'Id','')
        if not ident:continue
        name=data['Name' if dk else 'Nickname']
        metadata[ident]=dict(name=name,salary=float(data['Salary']),positions=set(data['Position'].split('/')),
                            team=data['TeamAbbrev' if dk else 'Team'],game=data['Game Info' if dk else 'Game'],
                            roster_position=data['Roster Position'] if dk else 'FLEX')
        if dk:mapping.setdefault(name,{})[data['Roster Position']]=ident
        else:mapping[name]=ident
    for row in pool.to_dict('records'):
        ident=str(row['DK_ID' if dk else 'FD_ID']).removesuffix('.0')
        original_name=metadata[ident]['name']
        mapping[row['Name']]=mapping[original_name]
    entry_rows=[r for r in rows[1:] if r and re.fullmatch(r'[1-9]\d*',r[0])]
    ids=[[mapping[name]['CPT' if j==0 else 'FLEX'] if dk else mapping[name]
          for j,name in enumerate(row)] for row in portfolio[slots].itertuples(index=False,name=None)]
    expected={r[0]:p for r,p in zip(entry_rows,ids)}
    if len(expected)!=len(portfolio):raise ValueError('Entry count mismatch')
    if dk:
        # Use the production export function without importing/executing the app.
        source=Path('dfs_app.py').read_text();tree=ast.parse(source)
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='build_dk_contest_entry_export')
        def fail(message):raise ValueError(message)
        st=SimpleNamespace(session_state={'dk_player_ids':mapping},error=fail,success=lambda *a:None,info=lambda *a:None,warning=lambda *a:None)
        scope={'st':st,'pd':pd,'re':re,'is_full_game_contest_name':lambda value:True}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'production-export','exec'),scope)
        header=rows[0][:10];header=[h+('.'+str(header[:i].count(h)) if h in header[:i] else '') for i,h in enumerate(header)]
        entries=pd.DataFrame([r[:10] for r in entry_rows],columns=header)
        lineups=pd.DataFrame(ids,columns=['CPT']+['FLEX']*5)
        first=scope[node.name](entries,contest['id'],lineups,['CPT']+['FLEX']*5,'Showdown')
        output=first.to_csv(index=False).encode()
        second=scope[node.name](first,contest['id'],lineups,['CPT']+['FLEX']*5,'Showdown').to_csv(index=False).encode()
    else:
        output,_=build_fanduel_entry_export(original,portfolio,mapping,contest,'Single Game')
        second,_=build_fanduel_entry_export(output,portfolio,mapping,contest,'Single Game')
    if output!=second:raise ValueError('Repeated replacement is not idempotent')
    checked=verify_entry_export(original,output,metadata,manifest['platform'],
                               'Showdown' if dk else 'Single Game',contest_ids=[contest['id']],expected_assignments=expected)
    return dict(contest_id=contest['id'],platform=manifest['platform'],**checked,
                repeated_replacement_identical=True,export_sha256=hashlib.sha256(output).hexdigest(),
                source_package_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                evidence='Regenerated from original template and frozen selector; not a captured submitted export.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packages',nargs='+');parser.add_argument('--output',required=True)
    args=parser.parse_args();report=[audit(path) for path in args.packages]
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()
