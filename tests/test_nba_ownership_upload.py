import unittest
import pandas as pd
from simmah_nba_ownership_upload import apply_snapshot, IMPORTED_COLUMN, OPTIMAL_COLUMN
from simmah_nba_ownership import COLUMN, field_ownership_inputs
from simmah_nba_ui import input_identity
from simmah_nba_auto_swap import input_signature
from simmah_nba_portfolio_limits import portfolio_limits


class NBAOwnershipUploadTests(unittest.TestCase):
    def fixture(self, platform='DraftKings'):
        own = 80 if platform == 'DraftKings' else 90
        pool = pd.DataFrame({'Player ID':list(map(str,range(10))),
            'Name':[f'Player {i} Jr.' for i in range(10)],'Team':['GSW']*10,
            'Projection':[30.]*10,'Projected Minutes':[32.]*10,
            'Injury Status':['Active']*10,COLUMN:[own]*10})
        pool.attrs['platform'] = platform
        frame = pd.DataFrame({'Player':[f'Player {i}' for i in range(10)],
            'Team':['Golden State Warriors']*10,'Position':['PG']*10,
            'Projected Ownership %':[own-40,own+10,own+10,own+10,own+10]+[own]*5,
            'Optimal %':[1.]*10,'Site':[platform]*10,'Sport':['NBA']*10,
            'Slate Date':['2026-11-06']*10,
            'Source':['https://www.fantasylabs.com/nba/simlabs/']*10,
            'Source Update ET':['10:50 AM EST']*10,'Captured UTC':['2026-11-06T20:49:37Z']*10})
        return pool,frame

    def apply(self,pool,frame):
        return apply_snapshot(pool,frame.to_csv(index=False).encode(),pool.attrs['platform'],'2026-11-06')

    def test_both_sites_match_preserve_projections_and_drive_field_and_caps(self):
        for platform in ('DraftKings','FanDuel'):
            with self.subTest(platform=platform):
                pool,frame=self.fixture(platform)
                result,meta=self.apply(pool,frame)
                pd.testing.assert_frame_equal(result[pool.columns],pool)
                self.assertNotIn(IMPORTED_COLUMN,pool)
                self.assertEqual(meta['matched_players'],10)
                self.assertEqual(result[OPTIMAL_COLUMN].tolist(),[1.]*10)
                inputs=field_ownership_inputs(result)
                self.assertEqual(inputs['mode'],'projected')
                self.assertIn('FantasyLabs',inputs['source'])
                self.assertEqual(inputs['weights'].tolist(),frame['Projected Ownership %'].tolist())
                self.assertEqual(portfolio_limits(result)['0']['Max Exposure %'],frame.iloc[0]['Projected Ownership %']+5)
                self.assertNotEqual(input_identity(pool,{}, {},0),input_identity(result,{}, {},0))
                locked=pd.Series(False,index=pool.index)
                self.assertNotEqual(input_signature(pool,locked),input_signature(result,locked))

    def test_reject_wrong_slate_invalid_values_duplicates_and_missing_players(self):
        for column,value in [('Site','FanDuel'),('Sport','NFL'),('Slate Date','2026-11-05'),
                             ('Team','Boston Celtics'),('Projected Ownership %','nan'),
                             ('Projected Ownership %',101),('Optimal %',-1),
                             ('Source','other')]:
            with self.subTest(column=column,value=value):
                pool,frame=self.fixture();frame=frame.astype(object);frame.loc[0,column]=value
                with self.assertRaises(ValueError):self.apply(pool,frame)
        pool,frame=self.fixture();frame.loc[0,'Player']='Player 1'
        with self.assertRaisesRegex(ValueError,'duplicate'):self.apply(pool,frame)
        pool,frame=self.fixture();pool.loc[0,'Name']='Missing Player'
        result,meta=self.apply(pool,frame)
        self.assertEqual(meta['missing_eligible_players'],['Missing Player'])
        self.assertEqual(field_ownership_inputs(result)['mode'],'relative popularity')
        pool,frame=self.fixture();frame['Projected Ownership %']=10
        with self.assertRaisesRegex(ValueError,'total'):self.apply(pool,frame)

    def test_inactive_salary_player_need_not_be_in_snapshot(self):
        pool,frame=self.fixture()
        pool.loc[10]=['10','Inactive Player','GSW',0,0,'Out',0]
        result,_=self.apply(pool,frame)
        self.assertTrue(pd.isna(result.loc[10,IMPORTED_COLUMN]))
        self.assertEqual(field_ownership_inputs(result)['mode'],'projected')

    def test_upload_visible_restored_and_removable(self):
        from streamlit.testing.v1 import AppTest
        from simmah_slate_workspaces import StoredUpload
        pool,frame=self.fixture()
        app=AppTest.from_string('''
import streamlit as st
from simmah_nba_ownership_upload import render_upload
st.session_state['result']=render_upload(st,st.session_state['pool'],'DraftKings','2026-11-06')
''')
        pool.loc[10]=['10','Unreported Player','GSW',20,20,'Active',80]
        app.session_state['pool']=pool
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.get('file_uploader')[0].proto.label,'FantasyLabs NBA ownership CSV')
        app.session_state['_slate_restored_uploads']={
            'nba_ownership_upload_DraftKings':StoredUpload(frame.to_csv(index=False).encode(),'ownership.csv')}
        app.run()
        self.assertFalse(app.exception)
        self.assertIn('10 matched players',app.success[0].value)
        self.assertIn('absent from this snapshot',app.warning[0].value)
        self.assertIn(IMPORTED_COLUMN,app.session_state['result'])
        app.button(key='nba_ownership_upload_DraftKings_remove_restored').click().run()
        self.assertFalse(app.exception)
        self.assertNotIn(IMPORTED_COLUMN,app.session_state['result'])

    def test_unreported_eligible_players_share_only_residual_and_keep_raw_blank(self):
        for platform in ('DraftKings','FanDuel'):
            pool,frame=self.fixture(platform)
            frame.loc[0,'Projected Ownership %']-=2
            for i in range(10,39):
                pool.loc[i]=[str(i),f'Unreported {i}','GSW',20,20,'Active',80]
            result,meta=self.apply(pool,frame)
            self.assertEqual(len(meta['missing_eligible_players']),29)
            self.assertTrue(result.loc[10:,IMPORTED_COLUMN].isna().all())
            self.assertTrue(result.loc[10:,OPTIMAL_COLUMN].isna().all())
            inputs=field_ownership_inputs(result)
            self.assertEqual(inputs['mode'],'projected')
            self.assertIn('estimated residual',inputs['source'])
            self.assertAlmostEqual(inputs['weights'][10:].sum(),2)
            self.assertAlmostEqual(inputs['weights'][0],frame.loc[0,'Projected Ownership %'])
            self.assertAlmostEqual(portfolio_limits(result)['10']['Max Exposure %'],5+2/29)
            pd.testing.assert_frame_equal(result[pool.columns],pool)
