"""Regression coverage for real post-lock CSV lifecycle and code activation."""
import csv
import io
import subprocess
import sys
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd

from test_nba_draftkings import template
from simmah_nba_candidates import build_candidates
from simmah_nba_import import read_template,read_workspace_template
from simmah_nba_late_swap import entry_rows,swap_entries,export_swaps,locked_players
from simmah_nba_rosters import export_entries
from simmah_slate_workspaces import snapshot,restore


class NBAEntryWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.original=template()
        self.pool=read_template(self.original)['players']
        self.pool['Projection']=np.arange(len(self.pool))+20.
        self.pool['Eligible']=True
        candidates=build_candidates(self.pool,np.random.default_rng(5).gamma(4,8,(80,len(self.pool))),target=10)
        self.lineups=[self.pool.iloc[x]['Player ID'].tolist() for x in candidates['indices'][:3]]
        self.filled=export_entries(self.original,self.lineups,'196711762',self.pool,salary_cap=50000,max_from_team=8)
        self.now=pd.Timestamp('2026-10-21T00:00:00Z')

    def current_download(self,status):
        rows=list(csv.reader(io.StringIO(self.filled.decode())))
        h=next(x for x in rows if 'Game Info' in x and 'ID' in x)
        col=h.index('Game Info')
        lookup=self.pool.set_index('Player ID')
        for row in rows[1:4]:
            for j,pid in enumerate(row[4:12],4):
                if lookup.loc[pid,'Team'] in {'NY','PHI'}:row[j]=f'Player ({pid}) (LOCKED)'
        for row in rows[rows.index(h)+1:]:
            if 'PHI@NYK' in row[col]:row[col]=status
        out=io.StringIO(newline='');csv.writer(out,lineterminator='\r\n').writerows(rows)
        return out.getvalue().encode()

    def test_in_progress_then_final_after_snapshot_restore_export_all_entries(self):
        state={'nba_import_game_context':self.pool}
        packed=snapshot(state);restored={};restore(restored,packed)
        pool=restored['nba_import_game_context']
        # News can remove its clock column; salary-file evidence must survive.
        pool['Game Start']=None
        for status in ('In Progress','Final'):
            with self.subTest(status=status):
                data=self.current_download(status)
                st=SimpleNamespace(session_state={'nba_import_game_context':pool})
                imported=read_workspace_template(st,SimpleNamespace(getvalue=lambda:data),nullcontext())
                self.assertEqual(imported['contests'][0]['owned_entries'],3)
                before=entry_rows(data,'196711762',pool)
                result=swap_entries(data,'196711762',pool,now=self.now,seconds=2)
                exported=export_swaps(data,'196711762',pool,result,now=self.now)
                after=read_template(exported,game_context_pool=pool)['entries']
                self.assertEqual([x[:4] for x in before],[x[:4] for x in after])
                locked=locked_players(pool,self.now)
                ids=dict(zip(pool['Player ID'],locked))
                for a,b in zip(before,after):
                    for slot,pid in enumerate(a[4:12],4):
                        if ids[pid]:self.assertEqual(b[slot],pid)
                src=list(csv.reader(io.StringIO(data.decode())))
                dst=list(csv.reader(io.StringIO(exported.decode())))
                self.assertEqual(src[4:],dst[4:])

    def test_missing_context_can_recover_without_replacing_current_rosters(self):
        data=self.current_download('Final')
        st=SimpleNamespace(session_state={},warning=lambda *args:None)
        original=SimpleNamespace(getvalue=lambda:self.original)
        with patch('simmah_nba_import.workspace_file_uploader',return_value=original):
            imported=read_workspace_template(st,SimpleNamespace(getvalue=lambda:data),nullcontext())
        self.assertEqual([x[4:12] for x in imported['entries']],self.lineups)
        self.assertIn('salary_game_starts',st.session_state['nba_import_game_context'].attrs)

    def test_projection_refresh_cannot_remove_salary_clocks(self):
        from simmah_nba_projections import apply_rotowire_projections,player_key
        details={player_key(r.Name,r.Team):{'Game Start':None} for r in self.pool.itertuples()}
        refreshed=apply_rotowire_projections(self.pool,{},details)
        self.assertEqual(refreshed['Game Start'].tolist(),self.pool['Game Start'].tolist())

    def test_release_refreshes_preloaded_reader_and_export_aliases(self):
        code="""
import simmah_nba_import as reader
import simmah_nba_ui as ui
from simmah_runtime_release import activate_nba_release
reader.read_template=lambda *_a,**_k: 'stale reader'
ui.export_portfolio=lambda *_a,**_k: 'stale export'
activate_nba_release('test-new-release')
from test_nba_draftkings import template
assert len(reader.read_template(template())['entries'])==3
import simmah_nba_pipeline as pipeline
assert ui.export_portfolio is pipeline.export_portfolio
before=reader.read_template
activate_nba_release('test-new-release')
assert reader.read_template is before
"""
        result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
