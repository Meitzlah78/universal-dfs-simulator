import base64,gzip,json
import streamlit as st
from simmah_slate_workspaces import restore,workspace_file_uploader
if not st.session_state.get('_fixture_restored'):
    key='nba_projection_upload_FanDuel'
    payload={'schema':1,'values':{key:None,key+'_remove_restored':False},'uploads':{key:{'name':'projections.csv','data':base64.b64encode(b'Player ID,Projection\n1,30\n').decode()}}}
    restore(st.session_state,base64.b64encode(gzip.compress(json.dumps(payload).encode())).decode())
    st.session_state['_fixture_restored']=True
value=workspace_file_uploader(st,'Optional NBA projections CSV',type=['csv'],key='nba_projection_upload_FanDuel')
st.write('Restored' if value else 'Removed')
