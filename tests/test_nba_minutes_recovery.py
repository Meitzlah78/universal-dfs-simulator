import unittest
import pandas as pd
from simmah_nba_minutes_recovery import restore_saved_minutes


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.old=pd.DataFrame([{'Player ID':'1','Name':'A','Team':'NY','Opponent':'PHI',
            'Game Start':'2026-10-21 19:00:00','Projection':20.,'Projected Minutes':30.,'Minutes Source':'RotoWire'}])
        self.current=self.old.copy();self.current['Projected Minutes']=None;self.current['Projection']=22.

    def test_provider_value_recovered_without_changing_projection(self):
        r=restore_saved_minutes(self.current,self.old,'2026-10-21')
        self.assertEqual(r['Projected Minutes'].iloc[0],30)
        self.assertEqual(r.Projection.iloc[0],22)
        self.assertEqual(r['Minutes Source'].iloc[0],'Last saved · RotoWire')
        self.assertEqual(r.attrs['saved_minutes_restored'],['A'])

    def test_other_date_or_ids_do_not_recover(self):
        self.assertTrue(restore_saved_minutes(self.current,self.old,'2026-10-22')['Projected Minutes'].isna().all())
        old=self.old.copy();old['Player ID']='2'
        self.assertTrue(restore_saved_minutes(self.current,old,'2026-10-21')['Projected Minutes'].isna().all())

    def test_explicit_zero_is_preserved(self):
        self.current['Projected Minutes']=0
        self.assertEqual(restore_saved_minutes(self.current,self.old,'2026-10-21')['Projected Minutes'].iloc[0],0)

    def test_estimated_or_newly_projected_player_is_not_filled(self):
        old=self.old.copy();old['Minutes Source']='Internal estimate'
        self.assertTrue(restore_saved_minutes(self.current,old,'2026-10-21')['Projected Minutes'].isna().all())
        old=self.old.copy();old['Projection']=None
        self.assertTrue(restore_saved_minutes(self.current,old,'2026-10-21')['Projected Minutes'].isna().all())


if __name__=='__main__':unittest.main()
