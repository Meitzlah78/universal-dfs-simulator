import streamlit as st
from simmah_slate_workspaces import snapshot,restore
from streamlit.runtime.scriptrunner import get_script_run_ctx
# Test a restore on the next run before widget instantiation.
if st.session_state.pop('_do_restore',False):restore(st.session_state,st.session_state['_saved_blob'])
st.number_input('Minimum salary',0,60000,0,key='test_salary')
if st.button('Save test snapshot',key='test_button'):
    states=get_script_run_ctx().session_state.get_widget_states()
    transient={key for key in st.session_state for widget in states if widget.WhichOneof('value')=='trigger_value' and widget.id.endswith('-'+key)}
    st.session_state['_saved_blob']=snapshot(st.session_state,transient)
if st.button('Restore test snapshot',key='test_restore'):
    st.session_state['_do_restore']=True;st.rerun()
