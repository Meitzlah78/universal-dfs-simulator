
import streamlit as st
from unittest.mock import patch
from simmah_saved_contests import render_panel
catalog={'schema':1,'contests':[{'format':'DraftKings Classic','id':'123','name':'Fixture','field_size':100,'entry_fee':.1}]}
key='saved_contest_choice_DraftKings Classic'
if '_slate_seeded_panel' not in st.session_state:
    for suffix in ('_use','_save','_restore_button','_backup','_restore'):st.session_state[key+suffix]=False if suffix!='_restore' else None
    st.session_state['_slate_seeded_panel']=True
with patch('simmah_saved_contests.load',return_value=catalog):
    result=render_panel(st,{'id':'123','entry_fee':.1},'DraftKings Classic')
st.session_state['_slate_panel_result']=result
