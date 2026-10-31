import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import base64,gzip,json
import pandas as pd
import streamlit as st
from simmah_slate_workspaces import restore,snapshot,workspace_data_editor
if '_slate_editor_seeded' not in st.session_state:
    payload={'schema':1,'values':{'game_lines_529f8237066490d6':{'@':'dict','value':[
        ['edited_rows',{'@':'dict','value':[['0',{'@':'dict','value':[['Game total',45.5],['Home spread',-3.5]]}]]}],
        ['added_rows',{'@':'list','value':[]}],['deleted_rows',{'@':'list','value':[]}]]},'salary':48000},'uploads':{}}
    blob=base64.b64encode(gzip.compress(json.dumps(payload).encode())).decode()
    restore(st.session_state,blob)
    st.session_state['_slate_editor_seeded']=True
base=pd.DataFrame({'Game':['DAL @ GB'],'Game total':[None],'Home spread':[None]})
result=workspace_data_editor(st,base,disabled=['Game'],key='game_lines_529f8237066490d6')
st.session_state['_slate_editor_result']=result
st.session_state['_slate_editor_snapshot']=snapshot(st.session_state)
