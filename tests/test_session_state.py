from collections.abc import Mapping
import ast
from pathlib import Path
import unittest
from simmah_session_state import safe_state_items

class StaleWidgetState(Mapping):
    def __iter__(self):return iter(['removed_widget','candidate_cache','unrelated_widget'])
    def __len__(self):return 3
    def __getitem__(self,key):
        if key=='removed_widget':raise KeyError(key)
        if key=='candidate_cache':return {'players':['Out Player']}
        return 'unchanged'

class SessionStateTests(unittest.TestCase):
    def test_reproduces_items_failure_and_skips_removed_key(self):
        state=StaleWidgetState()
        with self.assertRaises(KeyError):list(state.items())
        self.assertEqual(dict(safe_state_items(state)),{'candidate_cache':{'players':['Out Player']},'unrelated_widget':'unchanged'})
    def test_filter_precedes_value_lookup_and_preserves_cache_reference(self):
        value={'players':['Out Player']}
        class State(dict):
            def __getitem__(self,key):
                if key!='candidate_cache':raise AssertionError('Unrelated widget read')
                return super().__getitem__(key)
        state=State(candidate_cache=value,other_widget=False)
        rows=list(safe_state_items(state,lambda key:'candidate' in key))
        self.assertIs(rows[0][1],value)
        self.assertIn('Out Player',rows[0][1]['players'])
    def test_unexpected_errors_are_not_hidden(self):
        class State(dict):
            def __getitem__(self,key):raise RuntimeError('real failure')
        with self.assertRaises(RuntimeError):list(safe_state_items(State(cache=1)))
    def test_no_unsafe_session_items_in_main_app(self):
        tree=ast.parse((Path(__file__).resolve().parents[1]/'dfs_app.py').read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in {'items','values'}:
                self.assertNotEqual(ast.unparse(node.func.value),'st.session_state')
