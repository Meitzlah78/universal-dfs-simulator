import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('forecast_audit',Path(__file__).resolve().parents[1]/'scripts'/'validate_nfl_uploaded_forecasts.py')
audit_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit_module)

class ForecastValidationTests(unittest.TestCase):
    def fixture(self,root,later_actual=10):
        directory=Path(root)/'nfl_validation'/'test';directory.mkdir(parents=True,exist_ok=True)
        rows=[{'platform':'DraftKings','slate_date':'2026-11-01','player':'A','projection':10,'actual_points':8,'sim_mean':10},
              {'platform':'DraftKings','slate_date':'2026-11-02','player':'B','projection':10,'actual_points':later_actual,'sim_mean':10}]
        (directory/'projection_actuals.json').write_text(json.dumps({'rows':rows}))
        return directory,rows

    def test_later_actuals_never_change_fitted_correction(self):
        with tempfile.TemporaryDirectory() as root:
            self.fixture(root,1);first=audit_module.audit(root)
            self.fixture(root,100);second=audit_module.audit(root)
            self.assertEqual(first['platforms']['DraftKings']['fitted_point_adjustment'],second['platforms']['DraftKings']['fitted_point_adjustment'])
            self.assertNotEqual(first['platforms']['DraftKings']['holdout_candidate'],second['platforms']['DraftKings']['holdout_candidate'])
            self.assertFalse(second['promotion']['accepted'])

    def test_duplicate_or_missing_actuals_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            directory,rows=self.fixture(root);rows.append(rows[0])
            (directory/'projection_actuals.json').write_text(json.dumps({'rows':rows}))
            with self.assertRaisesRegex(ValueError,'Ambiguous'):audit_module.audit(root)
            rows=rows[:2];rows[1]['actual_points']=None
            (directory/'projection_actuals.json').write_text(json.dumps({'rows':rows}))
            with self.assertRaisesRegex(ValueError,'Missing'):audit_module.audit(root)

if __name__=='__main__':unittest.main()
