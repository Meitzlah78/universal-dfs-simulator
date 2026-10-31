"""Exercise actual Streamlit widget registration across a fresh app session."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from streamlit.testing.v1 import AppTest
import simmah_workspace_backup as backup

SOURCE='''
import streamlit as st
import numpy as np
import pandas as pd
from simmah_slate_workspaces import begin_workspaces,finish_workspaces,workspace_button
host=begin_workspaces(st)
st.number_input('Minimum salary',0,60000,0,key='minimum_salary')
if workspace_button(st,'Build',key='build_now'):
    st.session_state['portfolio']=pd.DataFrame({'QB':['Player A'],'Points':[151.125]})
    st.session_state['outcomes']=np.arange(2200000,dtype=float).reshape(10000,220)
finish_workspaces(st,host)
'''

class RebootAppTest(unittest.TestCase):
    def test_completed_build_and_salary_restore_into_fresh_widgets(self):
        with tempfile.TemporaryDirectory() as folder,patch.multiple(backup,ROOT=Path(folder)/'cache',STAGING=Path(folder)/'static'):
            app=AppTest.from_string(SOURCE,default_timeout=15)
            app.session_state['_slate_backup_booted']=True
            app.session_state['_slate_backup_owner']='a'*32
            row=dict(id='dk',name='DK.csv',data='b3JpZ2luYWwgY3N2')
            app.session_state['_slate_records']={'dk':row};app.session_state['_slate_active']=row
            app.run();self.assertFalse(app.exception)
            app.number_input(key='minimum_salary').set_value(49000).run()
            app.button(key='build_now').click().run();self.assertFalse(app.exception)
            cp=app.session_state['_slate_active']['_session_checkpoint']
            # Real widget button triggers and full outcome matrices are retained correctly.
            self.assertNotIn('build_now',cp['values'])
            ref=backup.write_backup('a'*32,backup.pack(dict(record=row,checkpoint=cp)))
            fresh=AppTest.from_string(SOURCE,default_timeout=15)
            fresh.session_state['_slate_backup_browser']=dict(event='boot-new',boot=dict(owner='a'*32,records=[{**ref,'id':'dk','name':'DK.csv','open':True,'revision':1}],active='dk'))
            fresh.run();self.assertFalse(fresh.exception)
            self.assertEqual(fresh.number_input(key='minimum_salary').value,49000)
            self.assertEqual(fresh.session_state['portfolio'].iloc[0]['Points'],151.125)
            np.testing.assert_array_equal(fresh.session_state['outcomes'],app.session_state['outcomes'])
            fresh.number_input(key='minimum_salary').set_value(49500).run()
            self.assertFalse(fresh.exception)
            self.assertEqual(fresh.session_state['portfolio'].iloc[0]['QB'],'Player A')

    def test_backup_is_downloaded_through_real_streamlit_static_route(self):
        from pathlib import Path
        from starlette.applications import Starlette
        import asyncio
        from streamlit.web.server.starlette.starlette_routes import create_app_static_serving_routes
        with tempfile.TemporaryDirectory() as folder:
            script=Path(folder)/'app.py';script.touch()
            root=Path(folder)/'static'/'workspace_backups'
            raw=b'verified backup HTTP bytes';ref=backup.write_backup('a'*32,raw,root)
            app=Starlette(routes=create_app_static_serving_routes(str(script),None))
            def get(path):
                events=[]
                async def receive():return {'type':'http.request','body':b'','more_body':False}
                async def send(event):events.append(event)
                scope=dict(type='http',asgi={'version':'3.0','spec_version':'2.4'},http_version='1.1',method='GET',scheme='http',path=path,raw_path=path.encode(),query_string=b'',headers=[],server=('localhost',80),client=('localhost',1234))
                asyncio.run(app(scope,receive,send))
                status=next(e['status'] for e in events if e['type']=='http.response.start')
                body=b''.join(e.get('body',b'') for e in events if e['type']=='http.response.body')
                return status,body
            status,content=get('/app/static/workspace_backups/'+'a'*32+'/'+ref['token']+'.zip')
            self.assertEqual(status,200);self.assertEqual(content,raw)
            self.assertEqual(get('/app/static/workspace_backups/'+'b'*32+'/'+ref['token']+'.zip')[0],404)
