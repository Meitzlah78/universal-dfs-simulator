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

    def test_saved_provider_zero_is_recovered_but_changed_projection_is_not(self):
        old=self.old.copy();old['Projected Minutes']=0.;old['Eligible']=False
        self.current['Projection']=20.
        result=restore_saved_minutes(self.current,old,'2026-10-21')
        self.assertEqual(result['Projected Minutes'].iloc[0],0)
        self.current['Projection']=21.
        self.assertTrue(restore_saved_minutes(self.current,old,'2026-10-21')['Projected Minutes'].isna().all())
        self.current['Projection']=20.;self.current['Expected Starter']=True
        self.assertTrue(restore_saved_minutes(self.current,old,'2026-10-21')['Projected Minutes'].isna().all())

    def test_persisted_snapshot_restores_sergio_zero_after_reboot(self):
        from simmah_nba_minutes_recovery import restore_verified_zero_snapshot
        current=pd.DataFrame([{'Player ID':'135636-248941','Name':'Sergio De Larrea',
            'Team':'DAL','Opponent':'HOU','Projection':6.79,'Projected Minutes':None,
            'Expected Starter':False}])
        result=restore_verified_zero_snapshot(current,'2026-10-21')
        self.assertEqual(result['Projected Minutes'].iloc[0],0)
        other=restore_verified_zero_snapshot(current,'2026-10-22')
        self.assertTrue(other['Projected Minutes'].isna().all())


if __name__=='__main__':unittest.main()
