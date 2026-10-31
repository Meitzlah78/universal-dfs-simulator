import streamlit as st
from simmah_slate_workspaces import begin_workspaces

begin_workspaces(st)
st.write('MAIN APP WORK')
st.write(st.session_state.get('restored_marker', 'not restored'))
