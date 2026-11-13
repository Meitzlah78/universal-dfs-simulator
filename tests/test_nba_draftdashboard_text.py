import unittest
import pandas as pd
from simmah_nba_draftdashboard_text import parse_text,apply_text

TEXT='''100
30
30
Player A
PF1
-$200 FD
ATL vs CHI
245.5\t$9,300
49.1
5.3 Value\t43.2
Last 3 Games:
32 | 48 | 0\t34
Last 3 Mins:
38 | 35 | 0\t25%
Last 3 Usage:
21% | 26% | 0%\t54
Last 3 CHI:
56 | 65 | 43\t<1%
Own\t49.1
Proj
5.3x
Value\t1.32
FPPM\t56%
Hit
(56% FD)
'''

class DDTextTests(unittest.TestCase):
    def pool(self):
        p=pd.DataFrame({'Player ID':['1'],'Name':['Player A'],'Team':['ATL'],
            'Opponent':['CHI'],'Salary':[9300],'Projection':[40.],
            'Projected Minutes':[30.],'Injury Status':['Active'],
            'RotoWire Projected Own %':[25.]})
        p.attrs.update(platform='DraftKings',slate_date='2026-11-13')
        return p

    def test_parse_types_and_censored_ownership_kept_separate(self):
        f=parse_text(TEXT,'DraftKings')
        self.assertEqual(f.iloc[0]['PRO'],49.1)
        self.assertEqual(f.iloc[0]['FPPG'],43.2)
        self.assertEqual(f.iloc[0]['MIN'],34.)
        self.assertEqual(f.iloc[0]['USE'],25.)
        self.assertEqual(f.iloc[0]['DraftDashboard Displayed OWN'],'<1%')
        self.assertEqual(f.iloc[0]['DraftDashboard Last 3 Minutes'],'38 | 35 | 0')
        self.assertNotIn('DraftDashboard Projected Own %',f)

    def test_apply_preserves_provider_ownership_and_original(self):
        p=self.pool();before=p.copy(deep=True)
        r=apply_text(p,TEXT,'DraftKings','2026-11-13',confirmed=True)
        self.assertEqual(r.loc[0,'Projection'],49.1)
        self.assertEqual(r.loc[0,'Projected Minutes'],34.)
        self.assertEqual(r.loc[0,'RotoWire Projected Own %'],25.)
        self.assertFalse(r.attrs['draftdashboard_text']['ownership_applied'])
        pd.testing.assert_frame_equal(p,before)

    def test_date_site_salary_and_opponent_guards(self):
        with self.assertRaisesRegex(ValueError,'Confirm'):apply_text(self.pool(),TEXT,'DraftKings','2026-11-13')
        with self.assertRaises(ValueError):parse_text(TEXT,'FanDuel')
        with self.assertRaises(ValueError):apply_text(self.pool(),TEXT,'DraftKings','2026-11-14',confirmed=True)
        for col,value in [('Salary',9000),('Opponent','BOS'),('Name','Missing')]:
            p=self.pool();p.loc[0,col]=value
            with self.subTest(col=col),self.assertRaises(ValueError):apply_text(p,TEXT,'DraftKings','2026-11-13',confirmed=True)

    def test_bad_or_incomplete_blocks_and_duplicates_reject(self):
        for text in [TEXT+TEXT,TEXT.replace('30\n30\n','31\n30\n'),TEXT.replace('Last 3 Mins:','Missing')]:
            with self.assertRaises(ValueError):parse_text(text,'DraftKings')

    def test_fd_and_missing_ownership_still_load_attributes(self):
        f=parse_text(TEXT.replace(' FD',' DK').replace('<1%','...'),'FanDuel')
        self.assertEqual(f.iloc[0]['DraftDashboard Displayed OWN'],'...')

    def test_text_changes_invalidate_saved_build(self):
        from simmah_nba_ui import input_identity
        p=self.pool();p['Position']='PF'
        a=input_identity(p,[],{},48000)
        p.attrs['draftdashboard_text']={'sha256':'new'}
        self.assertNotEqual(a,input_identity(p,[],{},48000))

    def test_attributes_csv_roundtrip_and_site_date_guards(self):
        f=parse_text(TEXT,'DraftKings')
        f['Site']='DraftKings';f['Sport']='NBA';f['Source']='DraftDashboard';f['Slate Date']='2026-11-13'
        r=apply_text(self.pool(),f.to_csv(index=False),'DraftKings','2026-11-13',confirmed=True,file_format='csv')
        self.assertEqual(r.Projection.iloc[0],49.1)
        self.assertEqual(r['DraftDashboard Displayed OWN'].iloc[0],'<1%')
        for col,value in [('Site','FanDuel'),('Slate Date','2026-11-14'),('Player','Other')]:
            bad=f.copy();bad[col]=value
            with self.subTest(col=col),self.assertRaises(ValueError):
                apply_text(self.pool(),bad.to_csv(index=False),'DraftKings','2026-11-13',confirmed=True,file_format='csv')

    def test_upload_requires_date_confirmation_then_applies_and_removes(self):
        from streamlit.testing.v1 import AppTest
        from simmah_slate_workspaces import StoredUpload
        app=AppTest.from_string('''
import streamlit as st
from simmah_nba_draftdashboard_text import render_text_upload
st.session_state['result']=render_text_upload(st,st.session_state['pool'],'DraftKings','2026-11-13')
''')
        app.session_state['pool']=self.pool()
        app.session_state['_slate_restored_uploads']={
            'nba_dd_text_DraftKings':StoredUpload(TEXT.encode(),'dd.txt')}
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['result'].Projection.iloc[0],40.)
        app.checkbox[0].check().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['result'].Projection.iloc[0],49.1)
        app.button(key='nba_dd_text_DraftKings_remove_restored').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['result'].Projection.iloc[0],40.)
