import ast
from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest


def app_tree():return ast.parse(Path('dfs_app.py').read_text())
def expander(node,label):
    return isinstance(node,ast.With) and any(isinstance(i.context_expr,ast.Call) and i.context_expr.args and isinstance(i.context_expr.args[0],ast.Constant) and i.context_expr.args[0].value==label for i in node.items)


class OptionalContestUITests(unittest.TestCase):
    def test_manual_roi_widgets_are_opt_in_and_history_is_kept(self):
        tree=app_tree()
        node=next(n for n in ast.walk(tree) if expander(n,'Advanced — optional tools'))
        # The shared container receives the opt-in ROI controls later in the app.
        gate=next(n for n in ast.walk(tree) if isinstance(n,ast.If) and isinstance(n.test,ast.Call) and n.test.args and isinstance(n.test.args[0],ast.Constant) and n.test.args[0].value=='Show manual ROI tracker')
        node.body=[gate]
        source='import streamlit as st\nst.session_state.setdefault("roi_history", [{"Contest Name":"saved"}])\n'+ast.unparse(node)
        app=AppTest.from_string(source).run()
        self.assertFalse(app.exception);self.assertFalse(app.checkbox[0].value)
        self.assertFalse(app.get('file_uploader'));self.assertFalse(app.number_input)
        self.assertFalse(app.expander[0].proto.expanded)
        self.assertEqual(app.session_state['roi_history'],[{'Contest Name':'saved'}])
    def test_payout_tools_stay_collapsed_and_missing_notice_is_outside(self):
        tree=app_tree();node=next(n for n in ast.walk(tree) if expander(n,'Advanced contest settings'))
        expanded=next(k.value.value for k in node.items[0].context_expr.keywords if k.arg=='expanded')
        self.assertFalse(expanded)
        notices=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and n.args and isinstance(n.args[0],ast.Constant) and str(n.args[0].value).startswith('Payout table missing:')]
        self.assertEqual(len(notices),1)
        self.assertGreater(notices[0].lineno,node.end_lineno)
        controls=[n.args[1].value for n in ast.walk(node) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in ('workspace_button','workspace_file_uploader') and len(n.args)>1 and isinstance(n.args[1],ast.Constant)]
        self.assertIn('FETCH DRAFTKINGS CONTEST DETAILS',controls)
        self.assertIn('Upload contest payout table CSV',controls)

if __name__=='__main__':unittest.main()
