"""Streamlit entry upload/restore/swap/export integration without network feeds."""
import csv,io
from contextlib import nullcontext
from types import SimpleNamespace
import numpy as np
import pandas as pd
import streamlit as st
from test_nba_draftkings import template
from simmah_nba_import import read_template,read_workspace_template
from simmah_nba_candidates import build_candidates
from simmah_nba_rosters import export_entries
from simmah_nba_late_swap import swap_entries,export_swaps
from simmah_slate_workspaces import snapshot,restore

original=template();pool=read_template(original)['players'];pool['Projection']=30.;pool['Eligible']=True
candidates=build_candidates(pool,np.random.default_rng(7).gamma(4,8,(80,len(pool))),target=10)
lineups=[pool.iloc[x]['Player ID'].tolist() for x in candidates['indices'][:3]]
filled=export_entries(original,lineups,'196711762',pool,salary_cap=50000,max_from_team=8)
status=st.selectbox('Download status',['Pregame','In Progress','Final'],key='download_status')
rows=list(csv.reader(io.StringIO(filled.decode())))
if status!='Pregame':
    h=next(x for x in rows if 'Game Info' in x and 'ID' in x);j=h.index('Game Info')
    for row in rows[rows.index(h)+1:]:
        if 'PHI@NYK' in row[j]:row[j]=status
out=io.StringIO();csv.writer(out).writerows(rows);data=out.getvalue().encode()
if st.button('Restore saved game context'):
    checkpoint=snapshot({'nba_import_game_context':st.session_state['nba_import_game_context']})
    recovered={};restore(recovered,checkpoint)
    st.session_state['nba_import_game_context']=recovered['nba_import_game_context']
if st.checkbox('Provider clock missing',key='clock_missing') and 'nba_import_game_context' in st.session_state:
    st.session_state['nba_import_game_context']['Game Start']=None
slate=read_workspace_template(st,SimpleNamespace(getvalue=lambda:data),nullcontext())
if slate is None:st.stop()
st.metric('Imported entries',len(slate['entries']))
pool=slate['players'];pool['Projection']=30.;pool['Eligible']=True
if st.button('Run fast late swap'):
    now=pd.Timestamp('2026-10-21T00:00:00Z')
    result=swap_entries(data,'196711762',pool,now=now,seconds=2)
    export=export_swaps(data,'196711762',pool,result,now=now)
    st.session_state['verified_export']=export
    st.metric('Export entries',len(read_template(export,game_context_pool=pool)['entries']))
    st.download_button('Download late swap CSV',export,'late-swap.csv','text/csv')
