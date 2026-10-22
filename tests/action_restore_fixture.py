import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import streamlit as st
from simmah_slate_workspaces import workspace_button,snapshot,restore
key='saved_contest_choice_DraftKings Classic_use'
if '_slate_seeded' not in st.session_state:
    st.session_state[key]=False
    st.session_state['future_action']=False
    st.session_state['salary']=48000
    st.session_state['_slate_seeded']=True
if workspace_button(st,'Use saved contest details',key=key):
    st.session_state['uses']=st.session_state.get('uses',0)+1
workspace_button(st,'Other action',key='future_action')
st.session_state['_slate_test_blob']=snapshot(st.session_state)
