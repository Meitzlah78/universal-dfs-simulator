import hashlib
import io
import json
import unittest
import gzip
import tempfile
from pathlib import Path
from unittest.mock import patch
import zipfile
import numpy as np
import pandas as pd
from simmah_nba_outcome_audit import audit_package, game_start, boxscore_actuals, render_audit


class OutcomeAuditTests(unittest.TestCase):
    def fixture(self, capture='2026-11-04T17:00:00Z', platform='DraftKings'):
        pool = pd.DataFrame([{'Player ID':'1','Name':'Player One','Team':'BOS','Opponent':'NY',
            'Eligible':True,'Projection':20,'Projected Minutes':30,'Game Start':'2026-11-04T19:00:00-05:00'},
            {'Player ID':'2','Name':'Absent Player','Team':'BOS','Opponent':'NY','Eligible':True,
             'Projection':10,'Projected Minutes':10,'Game Start':'2026-11-04T19:00:00-05:00'}])
        arrays=io.BytesIO();np.savez(arrays,outcomes_seed_83=np.tile([20.,10.],(100,1)))
        files={'inputs/player_pool.csv':pool.to_csv(index=False).encode(),'solver/arrays.npz':arrays.getvalue()}
        manifest={'kind':'nba_calibration_solver_package','contest_id':'1','platform':platform,
                  'captured_at_utc':capture,'files':{k:{'sha256':hashlib.sha256(v).hexdigest()} for k,v in files.items()}}
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z:
            for k,v in files.items():z.writestr(k,v)
            z.writestr('manifest.json',json.dumps(manifest))
        names=['MIN','PTS','3PT','REB','AST','STL','BLK','TO']
        row={'athlete':{'displayName':'Player One'},'stats':['30:30','20','2-4','10','10','1','1','2']}
        game={'date':'2026-11-04','event_id':'100','home_score':100,'away_score':90,
              'events':[{'homeScore':100,'awayScore':90}], 'boxscore':{'players':[
              {'team':{'abbreviation':'BOS'},'statistics':[{'names':names,'athletes':[row]}]},
              {'team':{'abbreviation':'NYK'},'statistics':[]}]}}
        return buf.getvalue(),game,row

    def test_exact_matching_scoring_and_missing_not_zero(self):
        raw,g,_=self.fixture();r=audit_package(raw,[g])
        self.assertEqual(len(r['rows']),1);self.assertEqual(len(r['omitted']),1)
        self.assertEqual(r['rows'][0]['actual'],56.)
        self.assertEqual(r['rows'][0]['actual_minutes'],30.5)
        self.assertEqual(r['summaries'][0]['above_p90'],1.)

    def test_fanduel_scoring(self):
        raw,g,_=self.fixture(platform='FanDuel')
        self.assertEqual(audit_package(raw,[g])['rows'][0]['actual'],51.)

    def test_explicit_dnp_is_zero(self):
        raw,g,row=self.fixture();row['didNotPlay']=True;row['stats']=[]
        self.assertEqual(audit_package(raw,[g])['rows'][0]['actual'],0.)

    def test_posttip_is_excluded(self):
        raw,g,_=self.fixture(capture='2026-11-05T00:00:00Z')
        r=audit_package(raw,[g]);self.assertEqual(r['status'],'pending');self.assertEqual(len(r['omitted']),2)

    def test_wrong_date_team_or_opponent_not_matched(self):
        for change in ('date','team','opponent'):
            raw,g,_=self.fixture()
            if change=='date':g['date']='2026-11-03'
            else:g['boxscore']['players'][0 if change=='team' else 1]['team']['abbreviation']='LAL'
            self.assertEqual(audit_package(raw,[g])['rows'],[])

    def test_duplicate_and_incomplete_games_fail(self):
        raw,g,_=self.fixture()
        with self.assertRaisesRegex(ValueError,'Ambiguous'):audit_package(raw,[g,g])
        g['home_score']=101
        with self.assertRaisesRegex(ValueError,'ledger'):audit_package(raw,[g])

    def test_tampered_arrays_fail(self):
        raw,g,_=self.fixture();buf=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(raw)) as source, zipfile.ZipFile(buf,'w') as target:
            for name in source.namelist():target.writestr(name,b'bad' if name.endswith('.npz') else source.read(name))
        with self.assertRaisesRegex(ValueError,'checksum'):audit_package(buf.getvalue(),[g])

    def test_provider_wall_clocks_are_eastern(self):
        self.assertEqual(game_start('2026-10-27 20:00:00').isoformat(),'2026-10-27T20:00:00-04:00')
        self.assertEqual(game_start('2026-11-04 20:00:00').isoformat(),'2026-11-04T20:00:00-05:00')

    def test_espn_team_aliases_and_unknown_minutes(self):
        _,g,row=self.fixture()
        g['boxscore']['players'][0]['team']['abbreviation']='UTAH'
        g['boxscore']['players'][1]['team']['abbreviation']='WSH'
        values=boxscore_actuals([g],'DraftKings')
        self.assertIn(('2026-11-04','player one','UTA','WAS'),values)
        row['stats'][0]='--'
        self.assertEqual(boxscore_actuals([g],'DraftKings'),{})

    def test_automatic_render_caches_and_rechecks_changed_results(self):
        from contextlib import nullcontext
        class UI:
            session_state={}
            def expander(self,*a,**k):return nullcontext()
            def caption(self,*a,**k):pass
            def dataframe(self,*a,**k):pass
            def warning(self,*a,**k):pass
        raw,g,_=self.fixture();ui=UI()
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/g['date'];folder.mkdir();file=folder/'100.json.gz'
            file.write_bytes(gzip.compress(json.dumps(g).encode()))
            with patch('simmah_nba_outcome_audit.audit_package', wraps=audit_package) as audit, patch('simmah_slate_workspaces.workspace_download_button'):
                render_audit(ui,raw,'build',tmp);render_audit(ui,raw,'lineups',tmp)
                self.assertEqual(audit.call_count,1)
                g['boxscore']['players'][0]['statistics'][0]['athletes'][0]['stats'][0]='31'
                file.write_bytes(gzip.compress(json.dumps(g).encode()))
                render_audit(ui,raw,'build',tmp)
                self.assertEqual(audit.call_count,2)

if __name__=='__main__':unittest.main()
