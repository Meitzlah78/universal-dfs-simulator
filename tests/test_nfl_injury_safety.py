import ast
import pickle
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo
import unittest
import pandas as pd
from simmah_nfl_injuries import InjuryStatuses,canonical_status,parse_injuries,reconcile_injuries,out_players
from simmah_session_state import safe_state_items

class Rerun(Exception):pass
class UI:
    def __init__(self,state=None):self.session_state=state if state is not None else {};self.messages=[]
    def __getattr__(self,name):
        if name=='rerun':return Mock(side_effect=Rerun)
        return lambda *args,**kwargs:self.messages.append((name,args))

def functions(st=None):
    names={'normalize_injury_player_name','normalize_injury_team','fetch_nfl_injury_statuses','apply_injury_statuses','lineup_export_download','automatic_projection_refresh'}
    nodes=[]
    for n in ast.parse(Path('dfs_app.py').read_text()).body:
        if isinstance(n,ast.FunctionDef) and n.name in names:n.decorator_list=[];nodes.append(n)
    ns={'st':st,'pd':pd,'ZoneInfo':ZoneInfo,'safe_state_items':safe_state_items,'requests':SimpleNamespace(get=Mock(side_effect=TimeoutError('feed timeout'))),
        'selected_format':'DraftKings Classic','_loaded_slate_tabs':None,'_pinned_slates':None,'workspace_stop':Mock(side_effect=RuntimeError('stopped')),
        'workspace_download_button':Mock(return_value='download'),'load_latest_automatic_pregame_snapshot':Mock(return_value=(pd.DataFrame(),{})),
        'save_export_checkpoint':Mock(),'refresh_public_projection_sources':Mock(return_value={'DFF':True})}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'injury_boundary','exec'),ns)
    return ns

def pool():return pd.DataFrame([{'Name':'Out Player','Team':'DAL'},{'Name':'Healthy Player','Team':'DAL'},{'Name':'Other Player','Team':'NYG'}])

class InjuryStateTests(unittest.TestCase):
    def setUp(self):
        self.ns=functions();self.name=self.ns['normalize_injury_player_name'];self.team=self.ns['normalize_injury_team']
    def apply(self,frame,incoming,state):return reconcile_injuries(frame,incoming,state,self.name,self.team)
    def snapshot(self):return InjuryStatuses({('outplayer','DAL'):'Out'},covered_teams={'DAL','NYG'})
    def test_outage_keeps_out_and_export_map_then_verified_recovery_clears_it(self):
        state={};self.apply(pool(),self.snapshot(),state)
        result,info=self.apply(pool(),{},state)
        self.assertEqual(result['Injury Status'].tolist(),['Out','Active','Active']);self.assertFalse(info['verified'])
        self.assertEqual(state['player_injury_statuses']['Out Player'],'Out')
        result,info=self.apply(pool(),InjuryStatuses({},covered_teams={'DAL','NYG'}),state)
        self.assertTrue(result['Injury Status'].eq('Active').all());self.assertTrue(info['changed'])
        self.assertEqual(state['player_injury_statuses']['Out Player'],'Active')
    def test_first_outage_is_unknown_not_verified_active(self):
        result,info=self.apply(pool(),{},{});self.assertTrue(result['Injury Status'].eq('Unknown').all())
    def test_upgrade_preserves_old_display_status(self):
        state={'display_injury_statuses':{'Out Player':'Out'}}
        r,_=self.apply(pool(),{},state);self.assertEqual(r['Injury Status'].iloc[0],'Out')
    def test_partial_feed_cannot_clear_an_unreported_team(self):
        state={};self.apply(pool(),InjuryStatuses({('otherplayer','NYG'):'Out'},covered_teams={'DAL','NYG'}),state)
        r,info=self.apply(pool(),InjuryStatuses({},covered_teams={'DAL'}),state)
        self.assertEqual(r['Injury Status'].iloc[2],'Out');self.assertEqual(info['unverified_slate_teams'],{'NYG'})
    def test_unknown_designation_preserves_prior_out(self):
        state={};self.apply(pool(),self.snapshot(),state)
        r,_=self.apply(pool(),InjuryStatuses({},covered_teams={'DAL'},uncertain_keys={('outplayer','DAL')}),state)
        self.assertEqual(r['Injury Status'].iloc[0],'Out')
    def test_unchanged_verified_snapshot_does_not_report_change(self):
        state={};self.apply(pool(),self.snapshot(),state)
        _,info=self.apply(pool(),self.snapshot(),state);self.assertFalse(info['changed'])
    def test_current_team_identity_does_not_match_another_team(self):
        r,_=self.apply(pd.DataFrame([{'Name':'Out Player','Team':'NYG'}]),self.snapshot(),{})
        self.assertEqual(r['Injury Status'].iloc[0],'Active')
    def test_parser_empty_uncovered_or_malformed_response_is_not_clearance(self):
        for p in [{},{'injuries':[]},{'injuries':[{'displayName':'Dallas Cowboys'}]},{'injuries':[{'displayName':'unknown','injuries':[]}]}]:
            with self.assertRaises(ValueError):parse_injuries(p,self.name,self.team)
    def test_explicit_empty_team_and_cache_pickle_preserve_coverage(self):
        x=parse_injuries({'injuries':[{'displayName':'Dallas Cowboys','injuries':[]}]},self.name,self.team)
        x=pickle.loads(pickle.dumps(x));self.assertEqual(x.covered_teams,{'DAL'});self.assertEqual(x,{})
    def test_comments_do_not_create_out_status_and_ir_aliases_work(self):
        self.assertIsNone(canonical_status('working out without restrictions'))
        for status in ['OUT','IR','Injured Reserve','Reserve/Injured','PUP','Suspended']:self.assertEqual(canonical_status(status),'Out')
        x=parse_injuries({'injuries':[{'team':{'abbreviation':'DAL'},'injuries':[{'athlete':{'fullName':'Out Player'},'shortComment':'without restrictions'}]}]},self.name,self.team)
        self.assertEqual(x,{});self.assertIn(('outplayer','DAL'),x.uncertain_keys)
    def test_team_aliases(self):
        self.assertEqual(self.team('JAC'),'JAX');self.assertEqual(self.team('LA'),'LAR')

class InjuryAppBoundaryTests(unittest.TestCase):
    def test_real_feed_timeout_keeps_known_out_excluded_without_marking_news(self):
        st=UI();ns=functions(st);st.session_state.update({'display_injury_statuses':{'Out Player':'Out'},'injury_feed_snapshot_previous':(('outplayer','DAL','Out'),)})
        r=ns['apply_injury_statuses'](pool(),'dk')
        self.assertNotIn('Out Player',r.Name.tolist());self.assertNotIn('injury_updates_found',st.session_state)
        self.assertTrue(any('Last known' in str(x) for _,x in st.messages))
    def test_all_four_export_formats_block_assigned_out_without_partial_download(self):
        formats={
          'DraftKings Classic':['QB','RB1','RB2','WR1','WR2','WR3','TE','FLEX','DST'],
          'DraftKings Showdown':['Captain','Flex1','Flex2','Flex3','Flex4','Flex5'],
          'FanDuel Full Roster':['QB','RB1','RB2','WR1','WR2','WR3','TE','FLEX','D'],
          'FanDuel Single Game':['MVP','FLEX1','FLEX2','FLEX3','FLEX4','FLEX5']}
        for fmt,slots in formats.items():
            with self.subTest(format=fmt):
                st=UI({'player_injury_statuses':{'Out Player':'Out'}});ns=functions(st);ns['selected_format']=fmt
                p=pd.DataFrame([{s:'Healthy Player' for s in slots},{s:'Out Player' if i==0 else 'Healthy Player' for i,s in enumerate(slots)}]);p['Entry ID']=['111','222'];old=p.copy(deep=True)
                self.assertIsNone(ns['lineup_export_download']('EXPORT',b'ids','entries.csv',portfolio=p,slots=slots))
                ns['workspace_download_button'].assert_not_called();ns['load_latest_automatic_pregame_snapshot'].assert_not_called();pd.testing.assert_frame_equal(p,old)
    def test_valid_export_keeps_download_and_checkpoint_arguments(self):
        st=UI({'player_injury_statuses':{'Out Player':'Out'}});ns=functions(st);p=pd.DataFrame({'QB':['Healthy Player']})
        self.assertEqual(ns['lineup_export_download']('EXPORT',b'ids','entries.csv',portfolio=p,slots=['QB']),'download')
        kw=ns['workspace_download_button'].call_args.kwargs;self.assertNotIn('portfolio',kw);self.assertNotIn('slots',kw);self.assertEqual(kw['args'][2],b'ids')
    def test_missing_roster_cannot_bypass_export_check(self):
        st=UI();ns=functions(st);self.assertIsNone(ns['lineup_export_download']('EXPORT',b'ids','entries.csv'));ns['workspace_download_button'].assert_not_called()
    def test_canonical_name_and_dk_name_id_match(self):
        ns=functions();p=pd.DataFrame({'QB':['O\'ut Player (1234)']})
        self.assertEqual(out_players(p,['QB'],{'Out Player':'Out'},ns['normalize_injury_player_name']),["O'ut Player"])
    def test_every_download_is_bound_to_its_actual_assigned_roster(self):
        calls=[n for n in ast.walk(ast.parse(Path('dfs_app.py').read_text())) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='lineup_export_download']
        self.assertEqual(len(calls),6)
        for c in calls:self.assertTrue({'portfolio','slots'}<={k.arg for k in c.keywords})
    def test_background_out_update_reruns_app_once_and_failure_never_reactivates(self):
        st=UI();ns=functions(st)
        reconcile_injuries(pool(),InjuryStatuses({},covered_teams={'DAL','NYG'}),st.session_state,ns['normalize_injury_player_name'],ns['normalize_injury_team'])
        ns['fetch_nfl_injury_statuses']=Mock(return_value=(InjuryStatuses({('outplayer','DAL'):'Out'},covered_teams={'DAL','NYG'}),'ESPN NFL injury feed'))
        with self.assertRaises(Rerun):ns['automatic_projection_refresh']('DraftKings Classic')
        self.assertEqual(st.session_state['player_injury_statuses']['Out Player'],'Out')
        self.assertTrue(st.session_state['injury_updates_found'])
        ns['automatic_projection_refresh']('DraftKings Classic')
        self.assertEqual(ns['fetch_nfl_injury_statuses'].call_count,1)
        # On the next scheduled check a failed feed still cannot clear the Out.
        st.session_state.pop('automatic_projection_last_check_draftkings_classic')
        ns['fetch_nfl_injury_statuses']=Mock(return_value=({},'unavailable'))
        ns['automatic_projection_refresh']('DraftKings Classic')
        self.assertEqual(st.session_state['player_injury_statuses']['Out Player'],'Out')
        self.assertTrue(any('could not refresh' in str(message) for _,message in st.messages))

if __name__=='__main__':unittest.main()
