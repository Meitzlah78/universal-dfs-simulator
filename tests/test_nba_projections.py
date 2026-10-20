import unittest
import pandas as pd
from simmah_nba_projections import parse_dff, apply_projections, slate_date

class NBAProjectionTests(unittest.TestCase):
    def setUp(self):
        self.pool=pd.DataFrame([{'Player ID':'1-1','Name':'A','Team':'NY','Opponent':'PHI','Injury Status':'Active'},
            {'Player ID':'1-2','Name':'B','Team':'PHI','Opponent':'NY','Injury Status':'Out'}])
    def test_date_and_matchup_guards(self):
        html='<tr data-start_date="2026-10-20" data-name="A" data-team="NY" data-opp="PHI" data-ppg_proj="40">'
        self.assertEqual(parse_dff(html,'2026-10-20',self.pool),{('a','NY'):40})
        for bad in [html.replace('2026-10-20','2026-10-21'),html.replace('PHI','BOS'),html.replace('40','nan')]:
            with self.assertRaises(ValueError):parse_dff(bad,'2026-10-20',self.pool)
        self.assertEqual(slate_date('FanDuel-NBA-2026-10-20-135251-entries.csv'),'2026-10-20')
    def test_uploaded_zero_has_priority_and_out_is_ineligible(self):
        result=apply_projections(self.pool,{('a','NY'):40,('b','PHI'):25},pd.DataFrame({'Player ID':['1-1'],'Projection':[0]}))
        self.assertTrue(result.Projection.isna().iloc[0])
        self.assertFalse(result.Eligible.any())
        self.assertEqual(result['Projection Source'].iloc[0],'Uploaded CSV')
    def test_cross_slate_upload_rejected(self):
        with self.assertRaises(ValueError):apply_projections(self.pool,{},pd.DataFrame({'Player ID':['9-9'],'Projection':[40]}))

class RotoWireNBATests(unittest.TestCase):
    def test_exact_slate_and_public_minutes(self):
        from simmah_nba_projections import select_rotowire_slate, parse_rotowire
        pool=pd.DataFrame([{'Team':'NY','Opponent':'PHI'}])
        payload={'slates':[{'slateID':1,'contestType':'Full Roster','startDateOnly':'2026-10-20','games':[9]}],
            'games':{'9':{'homeTeamCode':'NYK','visitTeamCode':'PHI','gameDate':'2026-10-20 19:00:00'}}}
        self.assertEqual(select_rotowire_slate(payload,'2026-10-20',pool)['slateID'],1)
        player={'slateID':7,'firstName':'Test','lastName':'Player','team':{'abbr':'NYK'},'opponent':{'team':'PHI'},
            'game':{'dateTime':'2026-10-20 19:00:00'},'minutes':32,'rostership':0,'stats':{'season':{'minutes':12}},'lineup':{'slot':'Yes','isConfirmed':False}}
        proj={'access':True,'source':'RotoWire','projections':[{'slateID':7,'pts':'40'}]}
        pts,details=parse_rotowire([player],proj,'2026-10-20',pool)
        self.assertEqual(pts[('test player','NY')],40)
        self.assertEqual(details[('test player','NY')]['Projected Minutes'],32)
        self.assertFalse(details[('test player','NY')]['Starter Confirmed'])
        self.assertEqual(details[('test player','NY')]['RotoWire RST % (unverified)'],0)
        with self.assertRaises(ValueError):parse_rotowire([player],proj,'2026-10-21',pool)
        proj['access']=False
        with self.assertRaises(ValueError):parse_rotowire([player],proj,'2026-10-20',pool)

class NBAProjectionUploadTests(unittest.TestCase):
    def test_entries_files_never_reach_rectangular_projection_parser(self):
        from simmah_nba_projections import read_projection_upload,EntriesInProjectionUpload
        for header in ['entry_id,contest_id,contest_name,entry_fee,PG','Entry ID,Contest Name,Contest ID,Entry Fee,PG']:
            ragged=(header+'\n1,2,3,4,5\n'+','.join(['salary']*32)).encode()
            with self.assertRaises(EntriesInProjectionUpload):read_projection_upload(ragged)
    def test_valid_projection_ids_and_zero_preserved(self):
        from simmah_nba_projections import read_projection_upload
        frame=read_projection_upload(b'Player ID,Projection\n001,0\n002,35.5\n')
        self.assertEqual(frame['Player ID'].tolist(),['001','002']);self.assertEqual(frame.Projection.iloc[0],0)
        with self.assertRaisesRegex(ValueError,'inconsistent columns'):read_projection_upload(b'Player ID,Projection\n1,20,extra\n')
