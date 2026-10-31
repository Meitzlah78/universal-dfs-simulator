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
