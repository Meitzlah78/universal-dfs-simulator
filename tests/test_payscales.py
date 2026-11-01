import json
import tempfile
import unittest
from pathlib import Path
from simmah_payscales import parse_tiers,validate_tiers,catalog,persist,reapply_showdown

class PayscaleTests(unittest.TestCase):
    def test_pasted_ranges(self):
        self.assertEqual(parse_tiers('1st | $250.00\n2nd–3rd | $150.00'),[[1,1,250.0],[2,3,150.0]])
    def test_reject_incomplete_or_increasing(self):
        for text in ('2,100','1,100\n3,50','1-2,100\n2,50','1,10\n2,20'):
            with self.assertRaises(ValueError):parse_tiers(text)
    def test_catalog_existing_saved_scales(self):
        rows=catalog(Path(__file__).resolve().parents[1]/'data')
        self.assertTrue(any(p['site']=='FanDuel' for p in rows.values()))
        self.assertTrue(any(p['site']=='DraftKings' for p in rows.values()))
        for p in rows.values():validate_tiers(p['payouts'])
    def test_persist_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'saved_payscales.json'
            rows={'example':{'name':'Example','site':'FanDuel','payouts':[[1,1,100]]}}
            persist(path,rows);self.assertEqual(catalog(Path(folder)),rows)
    def test_explicit_showdown_scale_wins_over_automatic_fetch(self):
        class State:pass
        st=State();st.session_state={'payscale_DraftKings Showdown_choice':'test','contest_payout_contest_id':'old'}
        reapply_showdown(st,{'id':'new','field_size':10,'payout_profile_id':'test','payouts':[[1,1,100],[2,3,10]]})
        self.assertEqual(st.session_state['contest_payout_contest_id'],'new')
        self.assertEqual(st.session_state['contest_payout_schedule'].sum(),120)

if __name__=='__main__':unittest.main()

class PanelTests(unittest.TestCase):
    def test_all_four_formats_apply_a_scale(self):
        from unittest.mock import patch
        from contextlib import nullcontext
        from simmah_payscales import render_panel
        class UI:
            def __init__(self,site):self.site=site;self.session_state={}
            def selectbox(self,label,options,**kw):
                choice=next(x for x in options if x and (x.startswith('dk:') if self.site=='DraftKings' else x.startswith('FanDuel:')))
                self.session_state[kw['key']]=choice
                return choice
            def write(self,*a,**k):pass
            def caption(self,*a,**k):pass
            def number_input(self,*a,**k):return k['value']
            def expander(self,*a,**k):return nullcontext()
            def text_input(self,*a,**k):return ''
            def text_area(self,*a,**k):return ''
        for fmt in ('DraftKings Classic','DraftKings Showdown','FanDuel Full Roster','FanDuel Single Game'):
            st=UI(fmt.split()[0]);active={'id':'123','field_size':1000000,'entry_fee':.1}
            with patch('simmah_payscales.workspace_button',return_value=False),patch('simmah_payscales.workspace_download_button'),patch('simmah_payscales.workspace_file_uploader',return_value=None):
                result=render_panel(st,active,fmt)
            self.assertTrue(result['payouts']);self.assertTrue(result['payout_profile_id'])
            self.assertEqual(result['id'],'123');self.assertEqual(result['field_size'],1000000)


class ContestScopedSelectionTests(unittest.TestCase):
    def ui(self):
        from contextlib import nullcontext
        class UI:
            def __init__(self):self.session_state={};self.choices=[]
            def selectbox(self,label,options,**kw):
                key=kw['key'];value=self.session_state.get(key,options[kw.get('index',0)])
                self.session_state[key]=value;self.choices.append((key,value));return value
            def write(self,*a,**kw):pass
            def caption(self,*a,**kw):pass
            def info(self,*a,**kw):pass
            def error(self,*a,**kw):raise AssertionError(a)
            def number_input(self,*a,**kw):return self.session_state.get(kw['key'],kw['value'])
            def expander(self,*a,**kw):return nullcontext()
            def text_input(self,*a,**kw):return ''
            def text_area(self,*a,**kw):return ''
        return UI()

    def render(self,st,active,fmt='DraftKings Classic'):
        from unittest.mock import patch
        from simmah_payscales import render_panel
        with patch('simmah_payscales.workspace_button',return_value=False),patch('simmah_payscales.workspace_download_button'),patch('simmah_payscales.workspace_file_uploader',return_value=None):
            return render_panel(st,active,fmt)

    def test_exact_uploaded_dime_package_initializes_correct_capacity(self):
        st=self.ui();active={'id':'today','name':'NFL $250 Dime Package [Just $0.10!]','entry_fee':.1,'field_size':260}
        result=self.render(st,active)
        self.assertEqual(result['field_size'],2972)
        self.assertEqual(sum((b-a+1)*p for a,b,p in result['payouts']),250)
        self.assertEqual(result['payouts'][-1],[284,698,.2])
        self.assertEqual(st.choices[-1][0],'payscale_DraftKings Classic_choice_today')

    def test_explicit_blank_and_manual_selection_survive_reruns(self):
        st=self.ui();key='payscale_DraftKings Classic_choice_today'
        active={'id':'today','name':'NFL $250 Dime Package [Just $0.10!]','entry_fee':.1,'field_size':2972}
        first=self.render(st,active);self.assertTrue(first['payout_profile_id'])
        st.session_state[key]=''
        result=self.render(st,active);self.assertNotIn('payout_profile_id',result)
        st.session_state[key]='DraftKings:250-nfl-dime-package-2972'
        result=self.render(st,active);self.assertTrue(result['payout_profile_id'])

    def test_second_contest_does_not_inherit_first_contest_choice(self):
        st=self.ui();first={'id':'one','name':'NFL $250 Dime Package [Just $0.10!]','entry_fee':.1,'field_size':260}
        result=self.render(st,first);self.assertEqual(result['field_size'],2972)
        second=self.render(st,{'id':'two','name':'Different contest','entry_fee':3.,'field_size':200})
        self.assertNotIn('payout_profile_id',second);self.assertEqual(second['field_size'],200)
        self.assertEqual(self.render(st,first)['field_size'],2972)

    def test_same_name_different_fee_is_not_automatically_applied(self):
        result=self.render(self.ui(),{'id':'other','name':'NFL $250 Dime Package [Just $0.10!]','entry_fee':1.,'field_size':2972})
        self.assertNotIn('payout_profile_id',result)
