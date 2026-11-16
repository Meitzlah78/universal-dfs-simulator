"""Regression: a valid diversity timeout must reach a populated FD download."""
import csv
import io
import unittest
from unittest.mock import patch
import pandas as pd
from streamlit.testing.v1 import AppTest
from simmah_selector_budget import VERSION

APP = '''
import streamlit as st
import pandas as pd
from simmah_nfl_portfolio import select_for_app
from simmah_exports import build_fanduel_entry_export
slots=['MVP','FLEX1','FLEX2','FLEX3','FLEX4','FLEX5']
names=list('ABCDEFG')
candidates=pd.DataFrame([names[:6],names[1:]],columns=slots)
candidates['Top1']=[.1,.09]
if 'assigned' not in st.session_state:
    st.session_state['assigned']=pd.DataFrame([['']*6]*2,columns=slots)
portfolio=select_for_app(st,candidates,slots,2,controls={},diversity=50,
    site='FanDuel',mode='Single Game',previous=st.session_state['assigned'])
if portfolio is not None:
    st.session_state['assigned']=portfolio
    template='entry_id,contest_id,MVP,flex,flex,flex,flex,flex\\n1,123-456,,,,,,\\n2,123-456,,,,,,\\n'
    data,count=build_fanduel_entry_export(template,portfolio,
        {name:str(i+1) for i,name in enumerate(names)}, {'id':'123-456'},'Single Game')
    st.session_state['export_bytes']=data
    st.dataframe(portfolio)
    st.download_button('Download assigned entries',data,file_name='FD.csv')
'''

class TimeoutExportUITests(unittest.TestCase):
    def test_blank_saved_entries_get_filled_download_without_acceptance(self):
        def timeout(frame,*args,**kwargs):
            result=frame.copy()
            result.attrs.update(portfolio_selection=VERSION,actual_quality_loss=0.,
                automatic_cap_pct=80.,diversity_optimal=False)
            return result
        with patch('simmah_nfl_portfolio.select_quality_budget',side_effect=timeout) as solver:
            app=AppTest.from_string(APP).run()
            self.assertFalse(app.exception)
            rows=list(csv.reader(io.StringIO(app.session_state['export_bytes'].decode())))
            self.assertEqual(len(rows),3)
            self.assertEqual([r[0] for r in rows[1:]],['1','2'])
            self.assertTrue(all(len(r[2:])==6 and all(r[2:]) for r in rows[1:]))
            self.assertEqual(len(app.get('download_button')),1)
            self.assertFalse(app.button)
            app.run()
            self.assertFalse(app.exception)
            self.assertEqual(solver.call_count,1)

if __name__=='__main__':unittest.main()
