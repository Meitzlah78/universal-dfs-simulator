import contextlib,unittest
from unittest.mock import patch
import pandas as pd
from simmah_selector_budget import VERSION,QualityNotCertified
from simmah_nfl_portfolio import select_for_app,preserve_existing,selection_key


class UI:
    def __init__(self,state=None):self.session_state=state or {};self.messages=[];self.buttons=set()
    def caption(self,x):self.messages.append(x)
    def warning(self,x):self.messages.append(x)
    def info(self,x):self.messages.append(x)
    def error(self,x):self.messages.append(x)
    def dataframe(self,*args,**kwargs):pass
    def expander(self,*args,**kwargs):return contextlib.nullcontext()
    def button(self,label,**kwargs):return label in self.buttons


def candidates():return pd.DataFrame([['A','B',.1,1],['C','D',.09,2],['E','F',.08,3]],columns=['X','Y','Top1','Mean'])
def selected(frame,timed_out=False):
    result=frame.iloc[:2].copy()
    result.attrs.update(portfolio_selection=VERSION,actual_quality_loss=0.,automatic_cap_pct=80.,
        diversity_optimal=not timed_out,quality_optimum=.19)
    return result


class UISelectionTests(unittest.TestCase):
    def test_failure_preserves_assignments_in_all_four_formats(self):
        for site,mode,legacy in [('DraftKings','Showdown','portfolio_df'),('DraftKings','Classic','classic_contest_entries_df'),('FanDuel','Single Game','fd_assigned_display_single_game'),('FanDuel','Full Roster','fd_full_roster_assigned_portfolio')]:
            old=candidates().iloc[:1].copy();st=UI({legacy:old,'selected_dk_contest':{'id':'d'},'selected_fd_contest':{'id':'f'}})
            preserve_existing(st.session_state);st.session_state.pop(legacy) # real build invalidation
            key=selection_key(st.session_state,site,mode)
            with patch('simmah_nfl_portfolio.select_quality_budget',side_effect=QualityNotCertified('quality-stage timeout')):
                result=select_for_app(st,candidates(),['X','Y'],2,controls={},diversity=50,site=site,mode=mode)
            self.assertIsNone(result);pd.testing.assert_frame_equal(st.session_state[key+'_recovery'],old)
            self.assertIn('failed',st.session_state[key+'_status']['status'])
            self.assertTrue(any('preserved' in m for m in st.messages))
    def test_timeout_does_not_replace_saved_without_user_action(self):
        old=candidates().iloc[2:].copy();st=UI({'portfolio_df':old});key=selection_key(st.session_state,'DraftKings','Showdown')
        with patch('simmah_nfl_portfolio.select_quality_budget',side_effect=lambda f,*a,**k:selected(f,True)):
            result=select_for_app(st,candidates(),['X','Y'],2,controls={},diversity=50,site='DraftKings',mode='Showdown',previous=old)
        self.assertIsNone(result);pd.testing.assert_frame_equal(st.session_state['portfolio_df'],old)
        st.buttons={'Use validated timeout portfolio'}
        result=select_for_app(st,candidates(),['X','Y'],2,controls={},diversity=50,site='DraftKings',mode='Showdown',previous=old)
        self.assertEqual(len(result),2);pd.testing.assert_frame_equal(st.session_state[key+'_previous'],old)
        st.buttons=set()
        self.assertIsNotNone(select_for_app(st,candidates(),['X','Y'],2,controls={},diversity=50,site='DraftKings',mode='Showdown',previous=old))
    def test_first_portfolio_can_use_valid_timeout_fallback(self):
        st=UI()
        with patch('simmah_nfl_portfolio.select_quality_budget',side_effect=lambda f,*a,**k:selected(f,True)):
            result=select_for_app(st,candidates(),['X','Y'],2,controls={},diversity=50,site='FanDuel',mode='Full Roster')
        self.assertEqual(len(result),2);self.assertFalse(result.attrs['diversity_optimal'])
        self.assertTrue(any('timed out' in m for m in st.messages))
    def test_table_sort_does_not_reselect_and_metrics_refresh(self):
        st=UI();c=candidates()
        with patch('simmah_nfl_portfolio.select_quality_budget',side_effect=lambda f,*a,**k:selected(f)) as solver:
            select_for_app(st,c,['X','Y'],2,controls={},diversity=50,site='DraftKings',mode='Classic')
            c=c.iloc[::-1].copy();c['Mean']=99
            result=select_for_app(st,c,['X','Y'],2,controls={},diversity=50,site='DraftKings',mode='Classic')
        self.assertEqual(solver.call_count,1);self.assertTrue(result.Mean.eq(99).all())
    def test_context_scope_and_missing_top1(self):
        st=UI({'selected_fd_contest':{'id':'one'}});a=selection_key(st.session_state,'FanDuel','Single Game')
        st.session_state['selected_fd_contest']={'id':'two'};b=selection_key(st.session_state,'FanDuel','Single Game');self.assertNotEqual(a,b)
        result=select_for_app(st,candidates().drop(columns='Top1'),['X','Y'],2,controls={},diversity=50,site='FanDuel',mode='Single Game')
        self.assertIsNone(result);self.assertTrue(any('CONTEST SIM' in m for m in st.messages))


if __name__=='__main__':unittest.main()
