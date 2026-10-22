import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import streamlit as st
from simmah_slate_workspaces import workspace_download_button,snapshot,restore
if '_slate_seeded' not in st.session_state:
    st.session_state['projection_accuracy_template_download']=False
    st.session_state['future_report_download']=False
    st.session_state['kept_salary']=48000
    st.session_state['_slate_seeded']=True
workspace_download_button(st,'Download Accuracy CSV Template',b'Name,Projection,ActualPoints\n',
    file_name='projection_accuracy_template.csv',key='projection_accuracy_template_download',on_click='ignore')
workspace_download_button(st,'Another report',b'player,score\n',key='future_report_download',on_click='ignore')
state={};restore(state,snapshot(st.session_state))
st.session_state['_slate_restored_test']=state
