import unittest
from types import SimpleNamespace
from unittest.mock import patch
import pandas as pd
from simmah_nba_confirmed import apply_confirmed_status,current_confirmed_pool
from simmah_nba_game_strip import game_records,team_lineup
from simmah_nba_lineups import render_live_strip
from simmah_nba_frame import data_view

class Evidence(dict):
    def __deepcopy__(self,memo):
        raise AssertionError('Lineup monitor copied raw provider evidence')

class MonitorTests(unittest.TestCase):
    def fixture(self):
        p=pd.DataFrame([dict(Name='Player '+str(i),Team='NY' if i<5 else 'PHI',
            Opponent='PHI' if i<5 else 'NY',Projection=30.,
            **{'Injury Status':'Active','Expected Starter':True,'Starter Confirmed':False}) for i in range(10)])
        p.attrs.update(slate_date='2026-11-18',saved_game_metadata_restored=True,
                       rotowire_provider_evidence=Evidence(raw=['payload']*1000))
        values={(r.Name.casefold(),r.Team):{'Expected Starter':True,'Starter Confirmed':True} for r in data_view(p).itertuples()}
        return p,values

    def test_lineup_changes_and_game_render_do_not_copy_evidence(self):
        p,values=self.fixture();view=apply_confirmed_status(p,values)
        self.assertIs(view.attrs['rotowire_provider_evidence'],p.attrs['rotowire_provider_evidence'])
        self.assertFalse(data_view(p)['Starter Confirmed'].any())
        self.assertTrue(data_view(view)['Starter Confirmed'].all())
        self.assertEqual(team_lineup(view,'NY')['status'],'Confirmed')
        self.assertTrue(game_records(view,[])[0]['saved_metadata'])
        pd.testing.assert_series_equal(data_view(view).Projection,data_view(p).Projection)

    def test_pending_and_stale_status_remain_visible(self):
        p,values=self.fixture();app=SimpleNamespace(session_state={})
        with patch('simmah_nba_confirmed.cached_confirmed_status',return_value={'players':values,'checked_at':100}):
            view,status=current_confirmed_pool(app,p,'2026-11-18',[('NY','PHI')])
        self.assertFalse(status['stale'])
        self.assertEqual(team_lineup(view,'PHI')['status'],'Confirmed')
        p['Expected Starter']=False;p.attrs['lineup_status_pending']=True
        self.assertEqual(team_lineup(p,'NY')['status'],'Checking')

    def test_monitor_remains_automatic_at_sixty_seconds(self):
        p,values=self.fixture()
        class App:
            session_state={}
            def fragment(self,**kwargs):
                self.interval=kwargs['run_every'];return lambda fn:fn
            def caption(self,*args):pass
            def markdown(self,*args,**kwargs):pass
        app=App()
        with patch('simmah_nba_confirmed.current_confirmed_pool',return_value=(p,{'stale':True})),patch('simmah_nba_game_strip.render_game_strip') as render:
            render_live_strip(app,p,[],None,'2026-11-18')
        self.assertEqual(app.interval,'60s');render.assert_called_once()
