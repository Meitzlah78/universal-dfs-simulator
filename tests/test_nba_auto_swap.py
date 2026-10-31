import unittest
import numpy as np
import pandas as pd
from simmah_nba_auto_swap import refresh_pool,input_signature


class AutoSwapTests(unittest.TestCase):
    def pool(self,site='DraftKings'):
        p=pd.DataFrame({'Player ID':['1','2'],'Name':['A','B'],'Team':['NY','NY'],
            'Opponent':['PHI','PHI'],'Projection':[10.,0.],
            'Game Start':['2099-10-21T19:00:00-04:00']*2,
            'Projection Source':['DFF','Uploaded CSV'],'Injury Status':['Active','Active']})
        p.attrs.update(platform=site,slate_date='2026-10-21');return p

    def rw(self,day,pool,platform):
        return {('a','NY'):20.,('b','NY'):30.},{('a','NY'):{'RotoWire Injury':'OUT'},
            ('b','NY'):{'RotoWire Injury':'Q'}},'123'

    def test_both_sites_news_and_uploaded_zero_priority(self):
        for site in ('DraftKings','FanDuel'):
            p=self.pool(site)
            out=refresh_pool(p,self.rw)
            self.assertEqual(out.Projection.tolist(),[20.,0.])
            self.assertEqual(out['Projection Source'].tolist(),['RotoWire','Uploaded CSV'])
            self.assertEqual(out['Injury Status'].tolist(),['Out','Questionable'])
            self.assertFalse(out.Eligible.any())
            self.assertEqual(p['Injury Status'].tolist(),['Active','Active'])
            self.assertEqual(out.attrs,p.attrs)

    def test_incomplete_news_blocks_export(self):
        with self.assertRaisesRegex(ValueError,'coverage'):
            refresh_pool(self.pool(),lambda *a,**kw:({}, {}, '1'))

    def test_feed_failure_propagates_not_zero(self):
        def fail(*a,**kw):raise OSError('offline')
        with self.assertRaises(OSError):refresh_pool(self.pool(),fail)

    def test_missing_rotowire_projection_stays_missing(self):
        def fresh(*args,**kwargs):
            return {},{('a','NY'):{'RotoWire Injury':'Active'},('b','NY'):{'RotoWire Injury':'Active'}},'123'
        out=refresh_pool(self.pool(),fresh)
        self.assertTrue(pd.isna(out.Projection.iloc[0]))
        self.assertEqual(out['Projection Source'].iloc[0],'Missing')
        self.assertFalse(out.Eligible.iloc[0])

    def test_locked_inputs_are_preserved(self):
        p=self.pool();p['Game Start']='2020-01-01T19:00:00-05:00'
        out=refresh_pool(p,self.rw)
        self.assertEqual(out.loc[0,'Projection'],10.)
        self.assertEqual(out.loc[0,'Projection Source'],'DFF')
        self.assertEqual(out.loc[0,'Injury Status'],'Active')

    def test_only_open_inputs_trigger_and_tipoff_changes_signature(self):
        p=self.pool();locks=np.array([True,False]);sig=input_signature(p,locks)
        p.loc[0,'Projection']=999
        self.assertEqual(sig,input_signature(p,locks))
        p.loc[1,'Injury Status']='Out'
        self.assertNotEqual(sig,input_signature(p,locks))
        self.assertNotEqual(input_signature(p,locks),input_signature(p,np.array([False,False])))


if __name__=='__main__':unittest.main()
