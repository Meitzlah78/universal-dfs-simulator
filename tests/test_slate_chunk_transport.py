import json
import unittest
from simmah_slate_transport import CHUNK_CHARS, outgoing, packet, receive_upload, advance_download, finish_upload, restart_download, restart_upload


class ChunkTransportTests(unittest.TestCase):
    def test_observed_48mb_snapshot_downloads_in_frames_below_25mb(self):
        state={};blob='x'*47810117
        args=dict(active='main',current=dict(id='main',name='main.csv',title='Main',data='CSV'),snapshot=blob,records=[])
        wire=outgoing(state,args)
        self.assertIsNone(wire['current']);self.assertEqual(wire['snapshot'],'')
        parts=[]
        while 'download' in wire:
            self.assertLess(len(json.dumps(wire).encode()),25000000)
            part=wire['download'];parts.append(part['data'])
            wire=advance_download(state,dict(id=part['id'],index=part['index']))
        restored=json.loads(''.join(parts))
        self.assertEqual(restored['snapshot'],blob)
        self.assertEqual(restored['current']['data'],'CSV')
        self.assertNotIn('_slate_download_transfer',state)
        self.assertNotIn('download',outgoing(state,args))

    def test_large_upload_does_not_replace_main_until_all_parts_are_complete(self):
        selected=dict(id='afternoon',name='afternoon.csv',title='Afternoon',data='CSV2',snapshot='S'*32000000)
        raw=json.dumps(dict(event='selection',selected=selected))
        total=(len(raw)+CHUNK_CHARS-1)//CHUNK_CHARS
        original=dict(id='main',snapshot='keep original')
        state={'_slate_active':original,'_slate_records':{'main':original}}
        for index in range(total):
            part=dict(id='transfer',index=index,total=total,data=raw[index*CHUNK_CHARS:(index+1)*CHUNK_CHARS])
            self.assertLess(len(json.dumps({'upload_part':part}).encode()),25000000)
            self.assertEqual(receive_upload(state,part),dict(id='transfer',index=index))
            receive_upload(state,part)  # Retry must not duplicate data.
            self.assertIs(state['_slate_active'],original)
            self.assertNotIn('_slate_pending',state)
        finish_upload(state,'transfer')
        self.assertEqual(state['_slate_pending'],selected)
        self.assertEqual(state['_slate_records']['main'],original)
        self.assertNotIn('_slate_upload_transfer',state)
        state.pop('_slate_pending');finish_upload(state,'transfer')
        self.assertNotIn('_slate_pending',state)

    def test_out_of_order_and_oversize_parts_preserve_saved_records(self):
        state={'_slate_records':{'main':{'snapshot':'keep'}}}
        for part in [dict(id='bad',index=1,total=2,data='x'),dict(id='bad',index=0,total=2,data='x'*(CHUNK_CHARS+1))]:
            with self.assertRaises(ValueError):receive_upload(state,part)
        self.assertEqual(state['_slate_records']['main']['snapshot'],'keep')

    def test_incomplete_upload_and_duplicate_download_acks_are_safe(self):
        state={}
        receive_upload(state,dict(id='partial',index=0,total=2,data='{"selected":'))
        finish_upload(state,'partial')
        self.assertNotIn('_slate_pending',state)
        wire=outgoing(state,dict(current={'id':'test'},snapshot='x'*(CHUNK_CHARS*3),records=[]))
        first=wire['download'];ack=dict(id=first['id'],index=0)
        next_part=advance_download(state,ack)['download']
        self.assertEqual(advance_download(state,ack)['download'],next_part)

    def test_streamlit_skips_main_work_during_chunks_and_restores_after_final_ack(self):
        import base64
        from pathlib import Path
        from streamlit.testing.v1 import AppTest
        from simmah_slate_workspaces import snapshot
        selected=dict(id='afternoon',name='afternoon.csv',title='Afternoon',
                      data=base64.b64encode(b'csv').decode(),snapshot=snapshot({'restored_marker':'SAVED BUILD'}))
        raw=json.dumps(dict(event='select-afternoon',selected=selected))
        midpoint=len(raw)//2
        app=AppTest.from_file(str(Path(__file__).with_name('slate_chunk_restore_fixture.py'))).run()
        for index,data in enumerate([raw[:midpoint],raw[midpoint:]]):
            app.session_state['loaded_slates_browser']={'event':f'part-{index}', 'upload_part':dict(id='restore',index=index,total=2,data=data)}
            app.run()
            self.assertFalse(app.exception)
            self.assertFalse(any(v.value=='MAIN APP WORK' for v in app.markdown))
        app.session_state['loaded_slates_browser']={'event':'done','upload_done':'restore'}
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['_slate_active']['id'],'afternoon')
        self.assertEqual(app.session_state['restored_marker'],'SAVED BUILD')
        self.assertTrue(any(v.value=='MAIN APP WORK' for v in app.markdown))

    def test_full_page_refresh_restarts_transfer_without_erasing_original(self):
        state={'_slate_records':{'main':{'snapshot':'keep'}}}
        wire=outgoing(state,dict(current={'id':'main'},snapshot='x'*(CHUNK_CHARS+20),records=[]))
        first=wire['download']
        advance_download(state,dict(id=first['id'],index=0))
        self.assertEqual(restart_download(state,first['id'])['download']['index'],0)
        receive_upload(state,dict(id='partial',index=0,total=2,data='{"selected":'))
        self.assertFalse(restart_upload(state,'partial'))
        self.assertNotIn('_slate_upload_transfer',state)
        self.assertEqual(state['_slate_records']['main']['snapshot'],'keep')


if __name__=='__main__':unittest.main()
