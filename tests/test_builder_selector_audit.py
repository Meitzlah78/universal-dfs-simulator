import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile
import numpy as np
import pandas as pd

spec=importlib.util.spec_from_file_location('builder_audit',Path(__file__).resolve().parents[1]/'scripts'/'audit_builder_selector.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class BuilderAuditTests(unittest.TestCase):
    def test_ties_split_prizes_and_reference_is_not_mutated(self):
        opponents=np.array([100.,100.,90.]);original=opponents.copy()
        rank,prize=m.standalone_metrics(np.array([100.,110.]),opponents,[[1,1,10],[2,2,5],[3,3,2]])
        np.testing.assert_array_equal(rank,[1,1]);self.assertAlmostEqual(prize[0],17/3)
        self.assertEqual(prize[1],10);np.testing.assert_array_equal(original,opponents)

    def test_role_and_unknown_scores_never_zero_fill(self):
        frame=pd.DataFrame({'Captain':['A','B','Unknown'],'Flex1':['B','A','A'],'Top1':[.9,.8,.7]})
        before=frame.copy(deep=True)
        points,supported=m.score_candidates(frame,['Captain','Flex1'],{'a':10,'b':2},True)
        np.testing.assert_array_equal(supported,[True,True,False]);np.testing.assert_allclose(points[:2],[17,13])
        self.assertTrue(np.isnan(points[2]));pd.testing.assert_frame_equal(frame,before)

    def test_unicode_and_interchangeable_slots(self):
        self.assertEqual(m.name_key('Dennis Schröder'),m.name_key('Dennis Schroder'))
        self.assertEqual(m.canonical(['A','B','C'],True),m.canonical(['A','C','B'],True))
        self.assertNotEqual(m.canonical(['A','B','C'],True),m.canonical(['B','A','C'],True))
        self.assertEqual(m.canonical(['B','A'],False),m.canonical(['A','B'],False))

    def test_tampered_nested_build_stops_before_reading_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'standings.csv').write_text('irrelevant')
            with ZipFile(root/'build.zip','w') as bundle:
                bundle.writestr('manifest.json',json.dumps({'files':{'original_build.zip':{'sha256':'0'*64}}}))
                bundle.writestr('original_build.zip',b'changed')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):
                m.audit(root/'build.zip',root/'standings.csv')

if __name__=='__main__':unittest.main()
