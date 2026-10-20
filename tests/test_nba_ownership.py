import unittest
import numpy as np
import pandas as pd
from simmah_nba_ownership import field_ownership_inputs,COLUMN
from simmah_nba_projections import parse_rotowire

class OwnershipTests(unittest.TestCase):
    def pool(self,platform='FanDuel'):
        p=pd.DataFrame({'Player ID':[str(i) for i in range(10)],'Projection':[30]*10,
             'Injury Status':['Active']*10,COLUMN:[90]*10,'RotoWire RST % (unverified)':[92]*10})
        p.attrs['platform']=platform
        return p
    def test_rounding_only_adjustment_and_inconsistent_fd_fallback(self):
        p=self.pool('DraftKings');p[COLUMN]=79.99
        r=field_ownership_inputs(p)
        self.assertEqual(r['mode'],'projected');self.assertAlmostEqual(r['weights'].sum(),800)
        p=self.pool();p[COLUMN]=100
        r=field_ownership_inputs(p)
        self.assertEqual(r['mode'],'relative popularity');np.testing.assert_array_equal(r['weights'],np.ones(10))
        self.assertIn('1000.0%',r['source'])
        p=p.drop(columns=COLUMN)
        self.assertEqual(field_ownership_inputs(p)['mode'],'relative popularity')
    def test_missing_and_zero_ownership_distinguished(self):
        p=self.pool();p.loc[0,COLUMN]=None
        self.assertEqual(field_ownership_inputs(p)['mode'],'relative popularity')
        p.loc[0,COLUMN]=0;p.loc[1:,COLUMN]=100
        self.assertEqual(field_ownership_inputs(p)['mode'],'projected')
    def test_dedicated_endpoint_overrides_metadata_only_for_ownership(self):
        pool=pd.DataFrame([{'Team':'NY','Opponent':'PHI'}])
        player={'slateID':7,'firstName':'Test','lastName':'Player','team':{'abbr':'NYK'},'opponent':{'team':'PHI'},
            'game':{'dateTime':'2026-10-20 19:00:00'},'minutes':32,'rostership':92}
        proj={'access':True,'source':'RotoWire','projections':[{'slateID':7,'pts':'40'}]}
        own={'access':True,'source':'RotoWire','rostership':[{'slateID':7,'rst':'12.3'}]}
        points,details=parse_rotowire([player],proj,'2026-10-20',pool,own)
        self.assertEqual(details[('test player','NY')][COLUMN],12.3)
        self.assertEqual(points[('test player','NY')],40)
        own['access']=False
        points,details=parse_rotowire([player],proj,'2026-10-20',pool,own)
        self.assertIsNone(details[('test player','NY')][COLUMN])
        self.assertEqual(points[('test player','NY')],40)
