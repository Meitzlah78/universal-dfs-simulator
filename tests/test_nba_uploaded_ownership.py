import io
import json
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from simmah_nba_draftdashboard_text import apply_text
from simmah_nba_ownership import field_ownership_inputs, ownership_column
from simmah_nba_ownership_upload import apply_snapshot


class UploadedOwnershipTests(unittest.TestCase):
    def fixture(self, platform='FanDuel'):
        pool = pd.DataFrame({'Player ID':[str(i) for i in range(20)],
            'Name':['Jarrett Allen']+[f'Player {i}' for i in range(1,20)],
            'Team':['CLE']*20,'Opponent':['MIA']*20,'Salary':[5800]*20,
            'Projection':[33.8]*20,'Projected Minutes':[30.]*20,
            'Injury Status':['Active']*20,'RotoWire Projected Own %':[2.]+[45.]*19})
        pool.attrs.update(platform=platform,slate_date='2026-11-13')
        frame = pd.DataFrame({'Player':pool.Name,'Team':pool.Team,'Opponent':pool.Opponent,
            'Salary':pool.Salary,'PRO':pool.Projection,'MIN':[25.]*20,
            'Site':platform,'Sport':'NBA','Source':'DraftDashboard','Slate Date':'2026-11-13',
            'DraftDashboard Displayed OWN':['34%']+['50%']*19})
        return pool,frame

    def apply(self, pool, frame):
        return apply_text(pool,frame.to_csv(index=False),pool.attrs['platform'],
                          '2026-11-13',confirmed=True,file_format='csv')

    def test_allen_upload_wins_and_both_sites_normalize_without_changing_raw(self):
        for site,expected in [('FanDuel',900),('DraftKings',800)]:
            pool,frame=self.fixture(site)
            result=self.apply(pool,frame)
            inputs=field_ownership_inputs(result)
            self.assertTrue(result.attrs['draftdashboard_text']['ownership_applied'])
            self.assertEqual(ownership_column(result),'DraftDashboard Projected Own %')
            self.assertEqual(result.loc[0,'DraftDashboard Raw Own %'],34)
            self.assertEqual(result.loc[0,'RotoWire Projected Own %'],2)
            self.assertEqual(result.loc[0,'Projected Minutes'],30)
            self.assertAlmostEqual(inputs['weights'].sum(),expected)
            self.assertAlmostEqual(inputs['weights'][0],34*expected/984)
            self.assertEqual(inputs['mode'],'projected')
            self.assertTrue(inputs['warnings'])
            self.assertNotIn('DraftDashboard Projected Own %',pool)

    def test_censored_missing_and_zero_have_distinct_provenance(self):
        pool,frame=self.fixture()
        frame.loc[1,'DraftDashboard Displayed OWN']='<1%'
        frame.loc[2,'DraftDashboard Displayed OWN']='...'
        frame.loc[3,'DraftDashboard Displayed OWN']='0%'
        result=self.apply(pool,frame)
        meta=result.attrs['draftdashboard_text']['ownership']
        self.assertEqual(result.loc[1,'DraftDashboard Raw Own %'],.5)
        self.assertTrue(pd.isna(result.loc[2,'DraftDashboard Raw Own %']))
        self.assertEqual(result.loc[2,'DraftDashboard Projected Own %'],45)
        self.assertEqual(result.loc[3,'DraftDashboard Projected Own %'],0)
        self.assertEqual(meta['estimated_players'],['Player 2'])
        self.assertEqual(len(meta['censored_player_keys']),1)
        self.assertEqual(field_ownership_inputs(result)['weights'][3],0)
        pool.loc[2,'RotoWire Projected Own %']=np.nan
        with self.assertRaisesRegex(ValueError,'finite'):
            self.apply(pool,frame)

    def test_invalid_or_incomplete_upload_does_not_apply_partially(self):
        pool,frame=self.fixture()
        for value in ('101%','-1%','garbage'):
            bad=frame.copy();bad.loc[1,'DraftDashboard Displayed OWN']=value
            with self.assertRaises(ValueError):self.apply(pool,bad)
        with self.assertRaisesRegex(ValueError,'missing eligible'):
            self.apply(pool,frame.iloc[:-1])
        self.assertNotIn('DraftDashboard Projected Own %',pool)

    def test_dedicated_complete_snapshot_normalizes_and_warns(self):
        pool,frame=self.fixture()
        frame['Position']='C/PF'
        frame['OWN']=frame.pop('DraftDashboard Displayed OWN').str.rstrip('%')
        frame['Source Update ET']='';frame['Captured UTC']=''
        result,meta=apply_snapshot(pool,frame.to_csv(index=False).encode(),'FanDuel','2026-11-13')
        self.assertEqual(meta['raw_total'],984)
        self.assertTrue(meta['warnings'])
        self.assertAlmostEqual(field_ownership_inputs(result)['weights'].sum(),900)

    def test_primary_upload_ui_applies_ownership_and_invalidates_build(self):
        from streamlit.testing.v1 import AppTest
        from simmah_slate_workspaces import StoredUpload
        from simmah_nba_ui import input_identity
        pool,frame=self.fixture()
        pool['Position']='C/PF'
        app=AppTest.from_string('''
import streamlit as st
from simmah_nba_draftdashboard_text import render_text_upload
st.session_state['result']=render_text_upload(st,st.session_state['pool'],'FanDuel','2026-11-13')
''')
        app.session_state['pool']=pool
        app.session_state['_slate_restored_uploads']={
            'nba_dd_text_FanDuel':StoredUpload(frame.to_csv(index=False).encode(),'dd.csv')}
        app.run()
        app.checkbox[0].check().run()
        self.assertFalse(app.exception)
        result=app.session_state['result']
        self.assertTrue(result.attrs['draftdashboard_text']['ownership_applied'])
        self.assertNotEqual(input_identity(pool,[],{},0),input_identity(result,[],{},0))
        self.assertTrue(any('950%' in warning.value for warning in app.warning))
        app.button(key='nba_dd_text_FanDuel_remove_restored').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(ownership_column(app.session_state['result']),'RotoWire Projected Own %')

    def test_provider_raw_payload_slate_and_request_times_retained(self):
        from simmah_nba_projections import download_rotowire
        listing={'slates':[{'slateID':91,'contestType':'Full Roster','startDateOnly':'2026-11-13','games':[1]}],
                 'games':{'1':{'homeTeamCode':'MIA','visitTeamCode':'CLE','gameDate':'2026-11-13'}}}
        player={'slateID':7,'firstName':'Jarrett','lastName':'Allen','team':{'abbr':'CLE'},
                'opponent':{'team':'MIA'},'game':{'dateTime':'2026-11-13 20:00:00'},'minutes':30}
        own={'access':True,'source':'RotoWire','rostership':[{'slateID':7,'rst':2}]}
        def get(request,timeout):
            url=request.full_url
            payload=(listing if 'slate-list' in url else [player] if 'players.php' in url else
                     own if 'rostership' in url else {'access':False})
            return io.BytesIO(json.dumps(payload).encode())
        evidence={}
        with patch('simmah_nba_projections.urlopen',side_effect=get):
            _,details,sid=download_rotowire('2026-11-13',pd.DataFrame([{'Team':'CLE','Opponent':'MIA'}]),evidence=evidence)
        self.assertEqual(sid,'91')
        self.assertEqual(evidence['provider_slate_id'],'91')
        record=evidence['requests']['rostership.php?slateID=91&rstSource=RotoWire']
        self.assertEqual(record['payload'],own)
        self.assertIn('+00:00',record['fetched_at_utc'])
        self.assertEqual(details[('jarrett allen','CLE')]['RotoWire Projected Own %'],2)
