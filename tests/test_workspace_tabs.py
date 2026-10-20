import ast,unittest
from pathlib import Path

class WorkspaceTabsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree=ast.parse(Path('dfs_app.py').read_text());cls.parents={child:parent for parent in ast.walk(cls.tree) for child in ast.iter_child_nodes(parent)}
    def contexts(self,node):
        found=[]
        while node in self.parents:
            node=self.parents[node]
            if isinstance(node,ast.With):found.extend(ast.unparse(i.context_expr) for i in node.items)
        return found
    def test_three_ordered_tabs(self):
        calls=[n for n in ast.walk(self.tree) if isinstance(n,ast.Call) and ast.unparse(n.func)=='st.tabs']
        self.assertEqual(len(calls),1);self.assertEqual(ast.literal_eval(calls[0].args[0]),['Contests','Roster & Projections','Build','Lineups'])
    def test_main_sections_are_routed(self):
        expected={'### Projection Sources':'_tab_roster','### Build Settings':'_tab_build','### Contest Selector':'_contest_setup','### Slate Setup':'_shared_header','### Player Pool — Stats, Simulation, Exposure & Controls':'_tab_roster'}
        counts={label:0 for label in expected}
        for n in ast.walk(self.tree):
            if isinstance(n,ast.Call) and ast.unparse(n.func)=='st.write' and n.args and isinstance(n.args[0],ast.Constant) and n.args[0].value in expected:
                label=n.args[0].value;self.assertIn(expected[label],self.contexts(n));counts[label]+=1
        self.assertTrue(all(counts.values()))
    def test_original_entry_widget_keys_remain_unique(self):
        keys=['universal_slate_setup_file','fd_selected_contest']
        for key in keys:
            count=sum(isinstance(n,ast.keyword) and n.arg=='key' and ((isinstance(n.value,ast.Constant) and n.value.value==key) or (key=='universal_slate_setup_file' and isinstance(n.value,ast.BinOp) and isinstance(n.value.left,ast.Constant) and n.value.left.value=='universal_slate_setup_file_')) for n in ast.walk(self.tree))
            self.assertEqual(count,1,key)

if __name__=='__main__':unittest.main()
