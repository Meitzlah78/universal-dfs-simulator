import streamlit as st
from simmah_slate_workspaces import begin_workspaces,finish_workspaces,workspace_rerun,select_upload,StoredUpload
host=begin_workspaces(st)
for site in ['DK','FD']:
    if st.button('Load '+site,key='load_'+site):
        select_upload(st,StoredUpload((site+',ID\n'+site+',123\n').encode(),site+'.csv'))
current=st.session_state.get('_slate_active')
if current:
    st.write('Active: '+current['name'])
    st.number_input('Minimum salary',min_value=0,max_value=60000,value=0,key='slate_salary')
    for sid,record in st.session_state.get('_slate_records',{}).items():
        if st.button('Switch '+record['name'],key='switch_'+record['name']):
            st.session_state['_slate_pending']=record
            workspace_rerun(st,host)
finish_workspaces(st,host)
