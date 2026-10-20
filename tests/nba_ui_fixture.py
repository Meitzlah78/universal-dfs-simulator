"""Synthetic Streamlit fixture; no live projections, engine runs or network."""
import csv,io
from types import SimpleNamespace
import numpy as np
import pandas as pd
import streamlit as st
import simmah_nba_ui as ui
from simmah_nba_import import SLOTS
from simmah_nba_pregame import ROLE_COLUMNS
from simmah_nba_candidates import build_candidates
from simmah_nba_contest import select_entries

pool=pd.DataFrame([{'Player ID':'135251-'+str(i),'Name':'Player '+str(i),
    'Position':['PG','SG','SF','PF','C'][i%5],'Salary':5000,
    'Team':['A','B','C','D'][i%4],'Opponent':['B','A','D','C'][i%4],
    'Injury Status':'Active','Projection':30,'Eligible':True,'Projected Minutes':24,
    'RotoWire RST % (unverified)':22.5,**{c:1 for c in ROLE_COLUMNS}} for i in range(40)])
rows=[['entry_id','contest_id','contest_name','entry_fee',*SLOTS]]
rows += [[str(900+i),'135251-281018991','Synthetic test','.05',*(['']*9)] for i in range(5)]
rows.append(['Id','Nickname','Salary','Position','Team','Opponent','Game','Injury Indicator','Injury Details','FPPG'])
for _,p in pool.iterrows():rows.append([p['Player ID'],p['Name'],'5000',p['Position'],p['Team'],p['Opponent'],p['Team']+'@'+p['Opponent'],'','','0'])
f=io.StringIO();csv.writer(f).writerows(rows)
upload=SimpleNamespace(name='FanDuel-NBA-2026-10-20-135251-entries.csv',getvalue=lambda:f.getvalue().encode())
slate={'players':pool,'contests':[{'id':'135251-281018991','name':'Synthetic test','entry_fee':.05,'owned_entries':5}]}
markets=[{'teams':('A','B'),'implied_points':(110,110)},{'teams':('C','D'),'implied_points':(110,110)}]

def fake_run(pool,engine,ownership,source,payouts,fee,count,**kwargs):
    st.session_state['test_build_calls']=st.session_state.get('test_build_calls',0)+1
    candidates=build_candidates(pool,np.random.default_rng(7).gamma(4,8,(100,40)),target=200)
    n=candidates['unique'];report=pd.DataFrame({'Top 1%':np.linspace(1,10,n),
        'Expected Prize ($)':np.linspace(.08,.12,n),'Entry Fee ($)':.05,
        'Expected ROI (%)':np.linspace(60,140,n)})
    portfolio=select_entries(pool,candidates['indices'],report,count,diversity=kwargs['diversity'])
    engine.last_report=[]
    return {'candidates':candidates,'report':report,'portfolio':portfolio,
        'field':{'entries':259739,'unique_rosters':1,'indices':candidates['indices'][:1],
                 'copies':np.array([259739]),'ownership_source':'Estimated synthetic test',
                 'ownership_sampled':np.full(40,22.5)}}
ui.run_pipeline=fake_run
st.session_state.setdefault('test_build_calls',0)
import time
import simmah_nba_lineups as lineup_module
pool['Expected Starter']=np.where(np.arange(len(pool))<20,'Yes','No')
pool['Starter Confirmed']=(pool['Team']=='A') & st.session_state.get('test_applied_confirmation',False)
def fake_status(sid,day,pairs):
    return {'players':{(r['Name'].casefold(),r['Team']):{
        'Expected Starter':'Yes' if i<20 else 'No',
        'Starter Confirmed':r['Team']=='A' and st.session_state.get('test_source_confirmed',False)} for i,r in pool.iterrows()},'checked_at':time.time()}
lineup_module.download_lineup_status=fake_status
def confirm_fixture():
    st.session_state['test_source_confirmed']=True
    st.cache_data(ttl=60,show_spinner=False,max_entries=8)(fake_status).clear()
def refresh_fixture():
    st.session_state['test_applied_confirmation']=st.session_state.get('test_source_confirmed',False)
    lineup_module.acknowledge_lineup_refresh(st.session_state)
st.button('Change source confirmation',key='test_source_change',on_click=confirm_fixture)
with st.container(key='sticky_projection_bar'):
    st.button('REFRESH',key='test_refresh',on_click=refresh_fixture)
header=st.container()
with header:lineup_module.render_live_strip(st,pool,markets,'29784','2026-10-20')
tabs=st.tabs(['Contest','Roster','Build','Lineups']);controls=st.container()
ui.render_workspace(st,slate,upload,tabs,controls,markets)
