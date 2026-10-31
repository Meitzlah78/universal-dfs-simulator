import base64
import csv
import io
import json
import os
import signal
import threading
import time
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from simmah_input_archive import Archive, inspect_input, sha256, standings_audit
from simmah_archive_ui import capture_upload, process_event, PREFIX


def standings(cid='123', final='0', copies=2):
    output=io.StringIO();writer=csv.writer(output)
    writer.writerow(['Rank','EntryId','EntryName','TimeRemaining','Points','Lineup'])
    for i in range(copies):
        writer.writerow([1,str(i),'not-persisted-in-audit',final,0,'CPT Alice Alpha FLEX Bob Beta FLEX Carol Gamma FLEX Daniel Delta FLEX Ethan Epsilon FLEX Frank Zeta'])
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w') as z:z.writestr('contest-standings-'+cid+'.csv',output.getvalue())
    return buf.getvalue()


def salaries(cid='123', pay=1000):
    output=io.StringIO();writer=csv.writer(output)
    writer.writerow(['Entry ID','Contest Name','Contest ID'])
    writer.writerow(['1','Test',cid])
    writer.writerow(['Position','Name + ID','Name','ID','Roster Position','Salary','Game Info','TeamAbbrev'])
    for i,name in enumerate('ABCDEFGH'):
        for role,mult in [('CPT',1.5),('FLEX',1)]:
            writer.writerow(['QB' if i<2 else 'WR',name+' ('+str(i)+')',name,str(i)+role,role,int(pay*mult),'A@B 10/23/2026 8:15PM ET','A' if i%2 else 'B'])
    return output.getvalue().encode()


class FakeBackup:
    def __init__(self):self.values={}
    def put(self,owner,key,raw):self.values[owner,key]=raw
    def get(self,owner,key):return self.values[owner,key]
    def records(self,owner):
        return [json.loads(raw) for (who,key),raw in self.values.items() if who==owner and key.startswith('metadata/')]


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.owner='a'*32

    def test_exact_bytes_hash_dedup_and_owner_isolation(self):
        a=Archive(self.root,self.owner);raw=salaries()
        r=a.put(raw,'../upload.csv');a.put(raw,'second-name.csv')
        self.assertEqual(len(a.files()),1);self.assertEqual(a.get(r['digest']),raw)
        self.assertEqual(a.files()[0]['filename'],'upload.csv')
        other=Archive(self.root,'b'*32)
        self.assertEqual(other.files(),[])
        with self.assertRaises(FileNotFoundError):other.get(r['digest'])

    def test_automatic_pair_runs_in_either_upload_order(self):
        for i,order in enumerate([('salary','contest'),('contest','salary')]):
            a=Archive(self.root,hex(i+1)[2:]*32)
            for kind in order:
                a.put(salaries() if kind=='salary' else standings(),kind+'.csv')
            jobs=a.plan();self.assertEqual(len(jobs),1);self.assertEqual(jobs[0]['state'],'queued')
            a.plan();self.assertEqual(len(a.jobs()),1)

    def test_wrong_contest_and_conflicting_salary_versions_do_not_fit(self):
        a=Archive(self.root,self.owner)
        a.put(salaries('999'),'wrong.csv');a.put(standings(),'standings.zip')
        self.assertEqual(a.plan(),[])
        a.put(salaries(),'correct.csv');a.put(salaries(pay=1100),'conflicting.csv')
        self.assertEqual(a.plan(),[])

    def test_standalone_salaries_without_contest_identity_do_not_guess(self):
        raw=salaries().split(b'Position,Name + ID',1)[1]
        a=Archive(self.root,self.owner)
        a.put(b'Position,Name + ID'+raw,'DKSalaries.csv');a.put(standings(),'contest.zip')
        self.assertEqual(a.plan(),[])
        files=a.files();s=next(r for r in files if r['metadata'].get('embedded_salary'));c=next(r for r in files if r['metadata'].get('kind')=='contest')
        a.bind_salary(c['digest'],s['digest']);self.assertEqual(a.plan()[0]['state'],'queued')

    def test_explicit_link_cannot_override_conflicting_contest_ids(self):
        a=Archive(self.root,self.owner)
        s=a.put(salaries('999'),'wrong.csv');c=a.put(standings(),'c.zip')
        with self.assertRaisesRegex(ValueError,'conflict'):a.bind_salary(c['digest'],s['digest'])

    def test_audit_and_score_names_not_exported(self):
        result=standings_audit(standings(),'standings.zip')
        self.assertEqual(result['complete_entries'],2)
        self.assertEqual(result['observed_equal_roster_pairs'],1)
        self.assertNotIn('not-persisted-in-audit',json.dumps(result))
        with self.assertRaisesRegex(ValueError,'not complete'):
            standings_audit(standings(final='30'),'x.zip')

    def test_failed_cloud_write_is_not_marked_durable(self):
        backup=FakeBackup()
        a=Archive(self.root,self.owner,backup)
        with patch.object(backup,'put',side_effect=OSError('network')):
            with self.assertRaises(OSError):a.put(salaries(),'x.csv')
        self.assertEqual(a.files()[0]['remote_ok'],0)
        self.assertEqual(a.get(a.files()[0]['digest']),salaries())
        a.put(salaries(),'x.csv');self.assertEqual(a.files()[0]['remote_ok'],1)

    def test_cloud_recovery_and_export_preserve_original(self):
        a=Archive(self.root,self.owner,FakeBackup());r=a.put(salaries(),'x.csv')
        (a.root/'objects'/r['digest']).unlink()
        self.assertEqual(a.get(r['digest']),salaries())
        with zipfile.ZipFile(io.BytesIO(a.backup_zip())) as z:
            manifest=json.loads(z.read('manifest.json'))
            self.assertEqual(manifest['files'][0]['digest'],r['digest'])
            self.assertEqual(z.read('originals/'+r['digest']+'/x.csv'),salaries())
        other=Archive(self.root,'b'*32)
        self.assertEqual(other.restore_zip(a.backup_zip()),1)
        self.assertEqual(other.get(r['digest']),salaries())

    def test_backup_corruption_is_rejected_before_any_save(self):
        a=Archive(self.root,self.owner)
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as z:
            digest=sha256(salaries())
            z.writestr('manifest.json',json.dumps(dict(schema=1,files=[dict(digest=digest,filename='x.csv')])))
            z.writestr('originals/'+digest+'/x.csv',b'tampered')
        with self.assertRaisesRegex(ValueError,'hash check'):a.restore_zip(data.getvalue())
        self.assertEqual(a.files(),[])

    def test_cloud_index_recovers_after_host_replacement(self):
        backup=FakeBackup();a=Archive(self.root,self.owner,backup)
        r=a.put(salaries(),'s.csv')
        b=Archive(self.root/'new-host',self.owner,backup)
        self.assertEqual(b.recover_remote_index(),1)
        self.assertEqual(b.get(r['digest']),salaries())
        other=Archive(self.root/'new-host','b'*32,backup)
        self.assertEqual(other.recover_remote_index(),0)

    def test_captain_is_preserved_and_flex_order_is_ignored(self):
        output=io.StringIO();w=csv.writer(output);w.writerow(['EntryId','TimeRemaining','Lineup'])
        for i,line in enumerate(['CPT Alice Alpha FLEX Bob Beta FLEX Carol Gamma FLEX Daniel Delta FLEX Ethan Epsilon FLEX Frank Zeta',
                                 'CPT Alice Alpha FLEX Frank Zeta FLEX Ethan Epsilon FLEX Daniel Delta FLEX Carol Gamma FLEX Bob Beta',
                                 'CPT Bob Beta FLEX Alice Alpha FLEX Carol Gamma FLEX Daniel Delta FLEX Ethan Epsilon FLEX Frank Zeta']):w.writerow([i,'0',line])
        r=standings_audit(output.getvalue().encode(),'x.csv')
        self.assertEqual(r['unique_rosters'],2);self.assertEqual(r['observed_equal_roster_pairs'],1)

    def test_browser_identity_recovery_hash_check_and_uploads(self):
        state={};st=SimpleNamespace(session_state=state)
        upload=SimpleNamespace(name='salary.csv',getvalue=salaries)
        capture_upload(st,[upload,upload],'primary')
        self.assertEqual(len(state[PREFIX+'pending']),1)
        raw=salaries();digest=sha256(raw)
        event=dict(event='1',owner=self.owner,hashes=[digest],restored=[dict(digest=digest,filename='salary.csv',data=base64.b64encode(raw).decode())])
        self.assertTrue(process_event(st,event));self.assertFalse(process_event(st,event))
        self.assertEqual(state[PREFIX+'owner'],self.owner)

    def test_all_original_upload_paths_call_archive(self):
        source=Path('simmah_slate_workspaces.py').read_text()
        self.assertIn("capture_upload(st,upload,'primary_slate_upload')",source)
        self.assertIn('capture_upload(st,value,key)',source)
        self.assertLess(source.index('capture_upload(st,value,key)'),source.index("if kwargs.get('accept_multiple_files'):return value"))
        html=Path('components/input_archive/index.html').read_text()
        self.assertNotIn('.delete(',html)
        self.assertIn('crypto.subtle.digest',html)

    def test_single_game_requires_two_teams_and_full_roster_is_not_mislabelled(self):
        a=Archive(self.root,self.owner)
        s=inspect_input(salaries(),'s.csv');s['mode']='full'
        c=inspect_input(standings(),'c.zip');c['mode']='full'
        a.put(salaries(),'s.csv',s);a.put(standings(),'c.zip',c)
        self.assertEqual(a.plan()[0]['state'],'unsupported_format')

    def test_runner_does_not_accept_a_success_flag_with_failed_metrics(self):
        import simmah_archive_jobs as runner
        a=Archive(self.root,self.owner)
        a.put(salaries(),'s.csv');a.put(standings(),'c.zip');job=a.plan()[0]
        def fake_run(argv,*args,**kwargs):
            out=Path(argv[argv.index('--output')+1]);out.mkdir()
            result=dict(status='verified_convergence',final_float64=dict(raw_gradient_max=.1,original_residual_max=.1,normalization_error=0),quad=dict(fresh_binary128=dict(raw_gradient_max=.1,original_residual_max=.1,normalization_error=0)))
            (out/'results.json').write_text(json.dumps(result))
            with zipfile.ZipFile(out.with_suffix('.zip'),'w') as z:z.writestr('results.json',json.dumps(result))
            return SimpleNamespace(returncode=0)
        with patch.object(runner.shutil,'which',return_value='/usr/bin/gcc'),patch.object(runner,'_run_calibration_process',side_effect=fake_run):
            runner.run_job(a,job)
        self.assertEqual(a.jobs()[0]['state'],'stopped_without_verified_convergence')

    @unittest.skipUnless(hasattr(signal,'SIGSTOP'),'Linux process-group pause required')
    def test_live_build_pauses_running_calibration_and_resumes_it(self):
        import simmah_archive_jobs as runner
        log=self.root/'ticks.log';errors=[];states=[]
        archive=SimpleNamespace(set_job=lambda jid,state,detail:states.append(state))
        def work():
            try:
                with log.open('w') as out:
                    runner._run_calibration_process([sys.executable,'-u','-c',
                        'import time\nfor i in range(100):\n print(i,flush=True)\n time.sleep(.01)'],
                        out,out,os.environ.copy(),5,archive,{'id':'test'})
            except Exception as error:errors.append(error)
        thread=threading.Thread(target=work);thread.start()
        token='test-live-build'
        try:
            end=time.monotonic()+2
            while (not log.exists() or log.stat().st_size==0) and time.monotonic()<end:time.sleep(.01)
            runner.begin_live_build(token);time.sleep(.1);before=log.stat().st_size
            time.sleep(.25);self.assertEqual(before,log.stat().st_size)
            runner.end_live_build(token);thread.join(3)
            self.assertFalse(thread.is_alive());self.assertFalse(errors)
            self.assertGreater(log.stat().st_size,before)
            self.assertIn('paused_for_build',states)
        finally:
            runner.end_live_build(token);thread.join(3)

    def test_live_build_defers_new_job_submission(self):
        import simmah_archive_jobs as runner
        archive=SimpleNamespace(plan=lambda:(_ for _ in ()).throw(AssertionError('Must defer')))
        runner.begin_live_build('test-defer')
        try:runner.queue_jobs(archive)
        finally:runner.end_live_build('test-defer')


if __name__=='__main__':unittest.main()
