import streamlit as st
import numpy as np
import pandas as pd
from unittest.mock import patch
from types import SimpleNamespace
from simmah_nba_cash import render_cash_check
from simmah_nba_rules import rules_for
pool=pd.DataFrame({'Player ID':[str(i) for i in range(40)],'Name':['Player '+str(i) for i in range(40)],
    'Projection':[30.]*40,'Team':['A']*40,'Position':['PG']*40})
pool.attrs['platform']=st.session_state.get('site','DraftKings')
size=len(rules_for(pool)['slots'])
def run(*args,**kwargs):
    st.session_state['cash_calls']=st.session_state.get('cash_calls',0)+1
    assert kwargs['selection_mode']=='flat_payout'
    assert kwargs['diversity']==kwargs['correlation']==0
    report=pd.DataFrame({slot:[str(i)] for i,slot in enumerate(rules_for(pool)['slots'])})
    report['Cash %']=70.;report['Evaluation Mean Points']=250.;report['Expected Prize ($)']=1.4
    return {'portfolio':report,'field':{}}
st.session_state.setdefault('nba_build_result',{'sentinel':'tournament unchanged'})
tabs=st.tabs(['Contests','Roster','Build','Lineups'])
with tabs[2],patch('simmah_nba_pipeline.run_pipeline',side_effect=run):
    render_cash_check(st,pool,SimpleNamespace(identity='test'),{'weights':np.ones(40),'source':'test','mode':'relative popularity'},
        48000,np.array([],dtype=int),'2026-10-31')
