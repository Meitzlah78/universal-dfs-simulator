import unittest
from unittest.mock import patch
from threading import Barrier
import pandas as pd
from simmah_nba_source_cache import load_sources
from simmah_nba_confirmed import parse_confirmed_page,current_confirmed_pool,cached_confirmed_status
from simmah_nba_game_strip import team_lineup
from simmah_nba_player_display import player_labels
from simmah_nba_game_context import has_game_context


class FakeStreamlit:
    def __init__(self):self.session_state={};self.cache={}
    def cache_data(self,**options):
        def decorate(fn):
            def call(*args):
                key=(fn.__name__,args)
                if key not in self.cache:self.cache[key]=fn(*args)
                return self.cache[key]
            return call
        return decorate


class LoadingTests(unittest.TestCase):
    def pool(self):
        return pd.DataFrame([{'Player ID':str(i),'Name':'Player '+str(i),'Team':'NY' if i<5 else 'PHI',
            'Opponent':'PHI' if i<5 else 'NY','Expected Starter':True,
            'Starter Confirmed':True,'Injury Status':'Active'} for i in range(10)])

    def test_sources_overlap_and_cache(self):
        state={};gate=Barrier(2);calls=[]
        def load(name):
            calls.append(name);gate.wait(timeout=2);return {'values':{name:1}}
        loaders={'a':lambda:load('a'),'b':lambda:load('b')}
        result=load_sources(state,'FD',loaders,now=100)
        self.assertEqual(set(calls),{'a','b'})
        self.assertEqual(result['a']['values'],{'a':1})
        load_sources(state,'FD',loaders,now=110)
        self.assertEqual(len(calls),2)

    def test_failure_backoff_force_and_identity(self):
        state={};calls=[]
        def fail():calls.append(1);raise OSError('feed down')
        loaders={'a':fail}
        state['a']={'identity':'FD','time':1,'values':{'player':20}}
        r=load_sources(state,'FD',loaders,now=1000)['a']
        self.assertEqual(r['values'],{'player':20})
        self.assertIn('error',r)
        load_sources(state,'FD',loaders,now=1001)
        self.assertEqual(len(calls),1)
        load_sources(state,'FD',loaders,now=1002,force=True)
        self.assertEqual(len(calls),2)
        r=load_sources(state,'DK',loaders,now=1003)['a']
        self.assertNotIn('values',r)
        self.assertEqual(len(calls),3)
        r=load_sources(state,'DK',{'a':lambda:{'values':{}}},now=1004,force=True)['a']
        self.assertNotIn('error',r)

    def test_partial_page_preserves_other_teams(self):
        players=''.join('<a href="/basketball/player/x" title="Player '+str(i)+'"></a>' for i in range(5))
        html='<div data-gamedate="2026-10-21"></div><div class="lineup" data-lnum="1"><div class="lineup__abbr">NY</div><div class="lineup__abbr">PHI</div><ul class="lineup__list is-visit"><li class="lineup__status is-confirmed"></li>'+players+'</ul><ul class="lineup__list is-home"></ul></div>'
        values=parse_confirmed_page(html,'2026-10-21',[('NY','PHI'),('MIL','WAS')])
        self.assertEqual(len(values),5)
        self.assertTrue(all(v['Starter Confirmed'] for v in values.values()))
        with self.assertRaises(ValueError):parse_confirmed_page(html,'2026-10-22',[('NY','PHI')])

    def test_failed_confirmation_is_cached(self):
        st=FakeStreamlit()
        with patch('simmah_nba_confirmed.download_lineup_page',side_effect=OSError('timeout')) as fetch:
            for _ in range(2):
                with self.assertRaises(ValueError):cached_confirmed_status(st,'2026-10-21',[('NY','PHI')])
            self.assertEqual(fetch.call_count,1)

    def test_same_slate_last_good_is_labeled_stale(self):
        st=FakeStreamlit();p=self.pool();pairs=(('NY','PHI'),)
        values={(r.Name.casefold(),r.Team):{'Expected Starter':True,'Starter Confirmed':True} for r in p.itertuples()}
        with patch('simmah_nba_confirmed.cached_confirmed_status',return_value={'players':values,'checked_at':100}):
            current_confirmed_pool(st,p,'2026-10-21',pairs)
        with patch('simmah_nba_confirmed.cached_confirmed_status',side_effect=OSError('timeout')):
            view,status=current_confirmed_pool(st,p,'2026-10-21',pairs)
            self.assertTrue(status['stale'])
            self.assertEqual(team_lineup(view,'NY')['status'],'Last confirmed')
            self.assertFalse(any('✅' in n for n in player_labels(p,view).values()))
            other,_=current_confirmed_pool(st,p,'2026-10-22',pairs)
            self.assertEqual(team_lineup(other,'NY')['status'],'Unavailable')

    def test_complete_context_skips_optional_schedule(self):
        p=self.pool();p['Game Start']='2026-10-21 19:00:00';p['Game Total']=230.
        p['Team Implied Points']=115.
        self.assertTrue(has_game_context(p))
        self.assertFalse(has_game_context(p.drop(columns='Game Start')))


if __name__=='__main__':unittest.main()
