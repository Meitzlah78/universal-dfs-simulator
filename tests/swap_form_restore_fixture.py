import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import hashlib,json,base64,gzip
import pandas as pd
import streamlit as st
from simmah_lineup_editor import render_editor
from simmah_slate_workspaces import encode,restore,snapshot
slots=['Captain','Flex1','Flex2','Flex3','Flex4','Flex5']
pool=pd.DataFrame({'Name':['A'+str(i) for i in range(7)],'Salary':[6000]*7,'Projection':[10.]*7,
    'Team':['DAL']*3+['GB']*4,'Opponent':['GB']*3+['DAL']*4,'Position':['WR']*7,'Injury Status':['Active']*7})
portfolio=pd.DataFrame([{slot:'A'+str(i) for i,slot in enumerate(slots)}]);portfolio['Salary']=39000
contest={'id':'123'}
fingerprint=json.dumps(['DraftKings','Showdown',portfolio[slots].astype(str).values.tolist(),pool[['Name','Salary']].astype(str).values.tolist(),contest],sort_keys=True,default=str)
key='manual_lineups_'+hashlib.sha256(fingerprint.encode()).hexdigest()[:20]
if '_slate_seeded_swap' not in st.session_state:
    values={'FormSubmitter:'+key+'_form-Apply player swap':False,key+'_apply_swap':False,key:encode(portfolio),'salary':48000}
    blob=base64.b64encode(gzip.compress(json.dumps({'schema':1,'values':values,'uploads':{}}).encode())).decode()
    restore(st.session_state,blob);st.session_state['_slate_seeded_swap']=True
current=render_editor(st,portfolio,pool,slots,'DraftKings','Showdown',contest)
st.session_state['_slate_swap_result']=current
st.session_state['_slate_swap_submit_key']=key+'_apply_swap'
st.session_state['_slate_swap_blob']=snapshot(st.session_state)
