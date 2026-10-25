import base64
import json
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from simmah_archive_ui import ArchiveTransferState, PREFIX, handle_archive_transfer
from simmah_input_archive import sha256
from simmah_slate_transport import receive_upload, outgoing, advance_download, CHUNK_CHARS


class ArchiveChunkTests(unittest.TestCase):
    def test_completed_upload_preserves_exact_original_and_isolates_slate_buffers(self):
        raw=b'original archive bytes'*100000
        digest=sha256(raw)
        payload=dict(event='restore-file',owner='a'*32,hashes=[digest],persistent=True,
                     restored=[dict(digest=digest,filename='build.zip',data=base64.b64encode(raw).decode())])
        encoded=json.dumps(dict(event=payload['event'],selected=payload))
        saved_slate={'id':'slate-transfer','parts':['keep unfinished slate']}
        state={'_slate_upload_transfer':saved_slate}
        scoped=ArchiveTransferState(state)
        total=(len(encoded)+CHUNK_CHARS-1)//CHUNK_CHARS
        for index in range(total):
            receive_upload(scoped,dict(id='archive-transfer',index=index,total=total,
                                      data=encoded[index*CHUNK_CHARS:(index+1)*CHUNK_CHARS]))
        state[PREFIX+'browser']=dict(event='done',upload_done='archive-transfer')
        st=SimpleNamespace(session_state=state)
        handle_archive_transfer(st)
        self.assertEqual(state[PREFIX+'pending'][digest]['raw'],raw)
        self.assertEqual(state['_slate_upload_transfer'],saved_slate)
        self.assertEqual(state[PREFIX+'owner'],'a'*32)
        handle_archive_transfer(st)
        self.assertEqual(len(state[PREFIX+'pending']),1)

    def test_download_completion_acknowledges_saved_file_hashes(self):
        state={};scoped=ArchiveTransferState(state)
        digest='b'*64
        wire=outgoing(scoped,dict(current={'records':[{'data':'x'*(CHUNK_CHARS+1)}]},snapshot='',records=[]))
        while 'download' in wire:
            part=wire['download'];wire=advance_download(scoped,dict(id=part['id'],index=part['index']))
        state[PREFIX+'browser']=dict(event='saved',download_received=wire['download_done'],owner='a'*32,hashes=[digest])
        handle_archive_transfer(SimpleNamespace(session_state=state))
        self.assertIn(digest,state[PREFIX+'browser_acked'])
        self.assertNotIn('_slate_download_saved',state)

    def test_partial_archive_upload_stops_before_main_app_work(self):
        state={PREFIX+'browser':dict(event='part',upload_part=dict(id='archive',index=0,total=2,data='{"selected":'))}
        class Stop(Exception):pass
        st=SimpleNamespace(session_state=state,stop=lambda:(_ for _ in ()).throw(Stop()))
        render=__import__('unittest.mock',fromlist=['Mock']).Mock()
        with patch('simmah_archive_ui.archive_component',return_value=render):
            with self.assertRaises(Stop):handle_archive_transfer(st)
        self.assertEqual(render.call_args.kwargs['upload_ack'],dict(id='archive',index=0))
        self.assertNotIn(PREFIX+'pending',state)


if __name__=='__main__':unittest.main()
