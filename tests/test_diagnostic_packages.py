import base64
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
import zipfile

import numpy as np
import pandas as pd
from simmah_nba_diagnostics import make_package,retain_package,package_reference,package_bytes
from simmah_diagnostic_packages import make_nfl_package,capture_nfl_build
from simmah_slate_workspaces import snapshot,decode


STAMP=datetime(2026,10,25,16,30,tzinfo=timezone.utc)


class DiagnosticPackageTests(unittest.TestCase):
    def nba(self):
        from test_nba_candidates import CandidateTests
        from simmah_nba_pipeline import run_pipeline
        pool,_=CandidateTests().fixture()
        pool['Player ID']=[str(1000+i) for i in range(len(pool))]
        pool['Name']=pool['Player ID'];pool['Opponent']='E'
        factory=lambda n,seed:np.random.default_rng(seed).gamma(4,8,(n,len(pool)))
        result=run_pipeline(pool,factory,np.full(len(pool),22.5),'synthetic',
            [1]*10+[0]*91,.05,5,simulations=20,candidate_target=100,
            field_support_target=500,capture_diagnostics=True)
        return pool,result,factory

    def test_nba_roundtrip_exact_outcomes_weights_hashes_and_immutability(self):
        pool,result,factory=self.nba()
        with TemporaryDirectory() as directory:
            Path(directory,'simmah_nba_example.py').write_text('version = 7\n')
            package=make_package(pool,result,b'original salary and entries',
                {'id':'42-99','capacity':105,'date':'2026-10-25'},[],{'control':'frozen'},
                started_at=STAMP.isoformat(),captured_at=STAMP,source_root=directory)
        name,raw,manifest=package
        self.assertIn('FanDuel_42-99_20261025T163000Z',name)
        self.assertEqual(manifest['missing_evidence'],[])
        self.assertEqual(manifest['field_dimensions']['entries'],100)
        with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
            for path,record in manifest['files'].items():
                self.assertEqual(sha256(bundle.read(path)).hexdigest(),record['sha256'])
            self.assertEqual(bundle.read('inputs/original_entries_salary.csv'),b'original salary and entries')
            with np.load(io.BytesIO(bundle.read('solver/arrays.npz')),allow_pickle=False) as arrays:
                for seed in (83,1092,2100):
                    np.testing.assert_array_equal(arrays['outcomes_seed_'+str(seed)],factory(20,seed))
            support=pd.read_csv(bundle.open('solver/fitted_support.csv'),dtype={c:str for c in ('PG','SG','SF','PF','C','GF','FC','UTIL1','UTIL2')})
            draws=np.random.default_rng(1094).multinomial(100,support['Probability'])
            regenerated=Counter()
            for row,count in zip(support.iloc[:,:9].itertuples(index=False,name=None),draws):
                if count:regenerated[tuple(sorted(row))]+=int(count)
            field=pd.read_csv(bundle.open('opponent_field.csv'),dtype={c:str for c in support.columns[:9]})
            actual=Counter()
            for row,count in zip(field.iloc[:,:9].itertuples(index=False,name=None),field['Copies']):actual[tuple(sorted(row))]+=int(count)
            self.assertEqual(regenerated,actual)
            frozen=bundle.read('inputs/player_pool.csv')
        pool.loc[0,'Salary']=1;result['field']['copies'][:]=999
        with zipfile.ZipFile(io.BytesIO(raw)) as bundle:self.assertEqual(bundle.read('inputs/player_pool.csv'),frozen)

    def test_invalid_field_count_blocks_misleading_package(self):
        pool,result,_=self.nba();result['field']['entries']+=1
        with self.assertRaisesRegex(ValueError,'count differs'):
            make_package(pool,result,b'x',{'id':'42'},[],{},started_at=STAMP.isoformat())

    def test_nfl_all_four_formats_have_original_and_binary_evaluation(self):
        formats=['DraftKings Classic','DraftKings Showdown','FanDuel Full Roster','FanDuel Single Game']
        pool=pd.DataFrame({'Name':['A','B'],'Salary':[5000,6000],'DK_ID':['1','2']})
        field=pd.DataFrame({'Captain':['A'],'Flex1':['B'],'Copies':[100]})
        values=pd.DataFrame([[1.25,2.5],[3.75,5.0]],columns=['A','B'])
        with TemporaryDirectory() as root:
            for label in formats:
                site='FanDuel' if label.startswith('FanDuel') else 'DraftKings'
                state={'selected_fd_contest':{'id':'fd'},'selected_dk_contest':{'id':'dk'},
                    '_slate_active':{'data':base64.b64encode(b'original upload').decode()},
                    'active_game_markets':{'A':24},'projection_api_key':'DO NOT SAVE',
                    'simulation_df':values,'diagnostic_package_current':{'data':b'old package'}}
                name,raw,manifest=make_nfl_package(state,label,pool,field,field,field,root,
                    extras={'evaluation_outcomes':values,'seed':123},source_root=root,captured_at=STAMP)
                self.assertIn('NFL',name);self.assertIn(manifest['contest_id'],name)
                with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
                    self.assertEqual(bundle.read('inputs/original_active_slate.csv'),b'original upload')
                    with np.load(io.BytesIO(bundle.read('solver/evaluation_outcomes.npz')),allow_pickle=False) as arrays:
                        np.testing.assert_array_equal(arrays['values'],values.to_numpy())
                    evidence=decode(json.loads(bundle.read('solver/runtime_state.json')))
                    self.assertEqual(evidence['active_game_markets'],{'A':24})
                    self.assertNotIn('projection_api_key',evidence)
                    self.assertNotIn('diagnostic_package_current',evidence)
                    for path,record in manifest['files'].items():self.assertEqual(sha256(bundle.read(path)).hexdigest(),record['sha256'])

    def test_automatic_archive_queues_once_and_slate_keeps_only_reference(self):
        st=SimpleNamespace(session_state={})
        manifest={'contest_id':'42','platform':'DraftKings','captured_at_utc':STAMP.isoformat()}
        package=('Simmah_NFL_42_Calibration_Solver.zip',b'package evidence',manifest)
        retain_package(st,package);retain_package(st,package)
        self.assertEqual(len(st.session_state['_slate_archive_pending']),1)
        reference=package_reference(package)
        self.assertEqual(package_bytes(st,reference),b'package evidence')
        st.session_state['diagnostic_package_current']=reference
        blob=snapshot(st.session_state)
        import gzip
        decoded=json.loads(gzip.decompress(base64.b64decode(blob)))
        self.assertNotIn('_slate_archive_pending',decoded['values'])
        self.assertNotIn('package evidence',str(decoded))
        self.assertEqual(decode(decoded['values']['diagnostic_package_current']),reference)

    def test_failed_capture_does_not_erase_build_results(self):
        from unittest.mock import patch
        st=SimpleNamespace(session_state={'lineups':'keep'},warning=lambda message:None)
        with patch('simmah_diagnostic_packages.make_nfl_package',side_effect=OSError('disk full')):
            capture_nfl_build(st,'DraftKings Classic',None,None,None,None,'.')
        self.assertEqual(st.session_state['lineups'],'keep')
        self.assertIn('disk full',st.session_state['diagnostic_package_error'])

    def test_latest_late_swap_keeps_original_build_without_recursive_archives(self):
        from simmah_diagnostic_updates import attach_latest_export
        st=SimpleNamespace(session_state={},warning=lambda message:None)
        original_manifest={'platform':'DraftKings','sport':'NFL','contest_id':'42',
            'captured_at_utc':STAMP.isoformat()}
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as bundle:bundle.writestr('manifest.json',json.dumps(original_manifest))
        base=('original_build.zip',buf.getvalue(),original_manifest)
        retain_package(st,base)
        target={**package_reference(base),'format':'DraftKings Classic','contest_id':'42'}
        st.session_state['diagnostic_package_current']=target
        context={'format':'DraftKings Classic','contest_id':'42','kind':'late_swap'}
        for number in ('first','last'):
            record={'archive':('export '+number).encode(),'exported_utc':STAMP.isoformat(),'export_id':number}
            attach_latest_export(st,record,context)
        self.assertEqual(target['original_build_reference'],package_reference(base))
        with zipfile.ZipFile(io.BytesIO(package_bytes(st,target))) as bundle:
            self.assertEqual(bundle.read('original_build.zip'),base[1])
            self.assertEqual(bundle.read('latest_export_checkpoint.zip'),b'export last')
            self.assertFalse(json.loads(bundle.read('manifest.json'))['submission_verified'])
            self.assertEqual(len([n for n in bundle.namelist() if n.endswith('.zip')]),2)
        before=dict(target)
        attach_latest_export(st,record,dict(context,contest_id='different'))
        self.assertEqual(target,before)

    def test_solver_report_includes_logs_and_sources_with_explicit_binary_omissions(self):
        from simmah_archive_jobs import _pack_attempt
        with TemporaryDirectory() as root:
            attempt=Path(root);(attempt/'sources').mkdir();(attempt/'engine').mkdir()
            (attempt/'stderr.log').write_text('solver stopped at memory budget')
            (attempt/'stdout.jsonl').write_text('{"iteration":4}\n')
            (attempt/'sources'/'entries.csv').write_text('exact original')
            (attempt/'engine'/'solver.c').write_text('original solver code')
            (attempt/'frontier.bin').write_bytes(b'rebuildable')
            raw=_pack_attempt(attempt)
        with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
            self.assertIn('memory budget',bundle.read('stderr.log').decode())
            self.assertIn('engine/solver.c',bundle.namelist())
            self.assertEqual(json.loads(bundle.read('package_manifest.json'))['omitted'][0]['path'],'frontier.bin')


if __name__=='__main__':unittest.main()
