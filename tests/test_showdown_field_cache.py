import ast
from pathlib import Path
import unittest
import numpy as np

class FieldCacheTests(unittest.TestCase):
    def test_batched_disk_scores_preserve_exact_scores_and_ties(self):
        tree=ast.parse(Path('dfs_app.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='showdown_sorted_field_cached')
        node.decorator_list=[]
        ns={'np':np}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'cache','exec'),ns)
        values=np.random.default_rng(37).integers(0,30,(300,12)).astype(np.float32)
        indices=np.array([[0,1,2,3,4,5],[5,4,3,2,1,0],[0,1,2,3,4,5],[6,7,8,9,10,11]])
        for multiplier in (1.,1.5):
            expected=values[21:290,indices].sum(axis=2)
            if multiplier!=1.:expected+=values[21:290,indices[:,0]]*(multiplier-1.)
            owner,actual=ns[node.name](values,indices,multiplier,21,290)
            np.testing.assert_array_equal(actual,np.sort(expected,axis=1))
            self.assertFalse(actual.flags.writeable)
            del actual
            owner.cleanup()
