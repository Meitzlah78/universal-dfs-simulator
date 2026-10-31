import unittest,io,zipfile,json,hashlib
import numpy as np,pandas as pd
from simmah_comparison_export import comparison_bundle,SLOTS

class BundleTests(unittest.TestCase):
    def inputs(self):
        rows=pd.DataFrame([list('abcdef')],columns=SLOTS)
        sims=pd.DataFrame(np.arange(60,dtype=np.float32).reshape(10,6),columns=list('abcdef'))
        return rows,pd.DataFrame({'Name':list('abcdef')}),rows.copy(),sims,{'id':'demo'}
    def test_roundtrip_and_integrity(self):
        args=self.inputs()
        with zipfile.ZipFile(io.BytesIO(comparison_bundle(*args))) as z:
            for name,digest in json.loads(z.read('hashes.json')).items():
                self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(),digest)
            actual=np.load(io.BytesIO(z.read('scenarios.npz')),allow_pickle=False)['points']
            np.testing.assert_array_equal(actual,args[3].to_numpy())
            self.assertEqual(actual.dtype,np.float32)
            self.assertEqual(json.loads(z.read('scenario_player_names.json')),list('abcdef'))
    def test_stale_incompatible_session_rejected(self):
        args=list(self.inputs());args[3]=args[3].rename(columns={'a':'wrong'})
        with self.assertRaises(ValueError):comparison_bundle(*args)
