import unittest
import numpy as np
import pandas as pd
from simmah_field_popularity import estimated_field_weights
from simmah_footballguys import has_uploaded_ownership

class FieldPopularityTests(unittest.TestCase):
    def test_projection_magnitude_and_value_are_preserved(self):
        pool=pd.DataFrame({'Projection':[20.,.1,20.],'Salary':[8000,4000,6000]})
        w=estimated_field_weights(pool,[1,100,1])
        self.assertGreater(w[0]/w[1],10000)
        self.assertGreater(w[2],w[0])
        self.assertTrue(np.isfinite(w).all())
    def test_public_preferences_use_external_projection_not_simulated_mean(self):
        p=pd.DataFrame({'Projection':[10,20],'Salary':[5000,5000]})
        np.testing.assert_array_equal(estimated_field_weights(p,[100,1]),estimated_field_weights(p,[1,100]))
    def test_player_identity_and_row_order_do_not_change_preferences(self):
        p=pd.DataFrame({'Name':['A','B','C'],'Projection':[10,20,5],'Salary':[5000,7000,4000]})
        expected=estimated_field_weights(p,[10,20,5]);p.Name=['X','Y','Z']
        np.testing.assert_array_equal(expected,estimated_field_weights(p,[10,20,5]))
        np.testing.assert_array_equal(expected[::-1],estimated_field_weights(p.iloc[::-1],[5,20,10]))
    def test_blank_invalid_ownership_does_not_block_automatic_loader(self):
        for vals in [[None,np.nan],['', 'inf'],[-1,101]]:
            self.assertFalse(has_uploaded_ownership(pd.DataFrame({'Projected Own %':vals})))
        self.assertTrue(has_uploaded_ownership(pd.DataFrame({'Projected Own %':['0%',None]})))
    def test_nonfinite_inputs_and_zero_projections(self):
        w=estimated_field_weights(pd.DataFrame({'Projection':[0,np.nan,10],'Salary':[4000,5000,6000]}),[20,5,10])
        self.assertEqual(w[0],0);self.assertGreater(w[1],0)
        with self.assertRaises(ValueError):estimated_field_weights(pd.DataFrame({'Projection':[0]}),[0])
