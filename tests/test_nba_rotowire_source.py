"""Single-provider NBA setup regression fixtures; no live provider calls."""
import unittest
import pandas as pd
from simmah_nba_projections import apply_rotowire_projections
from simmah_nba_ownership import field_ownership_inputs


class RotoWireSourceTests(unittest.TestCase):
    def pool(self):
        return pd.DataFrame([
            {'Player ID':str(i),'Name':'Player '+str(i),'Team':'NY','Opponent':'PHI',
             'Projection':99.,'Projection Source':'DFF','Injury Status':'Active'}
            for i in range(10)])

    def test_missing_rotowire_player_does_not_keep_dff_projection(self):
        p=self.pool()
        result=apply_rotowire_projections(p,{('player 0','NY'):25.},
            {('player 0','NY'):{'Projected Minutes':30.,'Minutes Source':'RotoWire'}})
        self.assertEqual(result.Projection.iloc[0],25.)
        self.assertEqual(result['Projection Source'].iloc[0],'RotoWire')
        self.assertTrue(result.Projection.iloc[1:].isna().all())
        self.assertFalse(result.Eligible.iloc[1:].any())
        self.assertTrue(p.Projection.eq(99.).all())

    def test_missing_minutes_remain_unknown_and_uploaded_zero_wins(self):
        values={('player 0','NY'):25.,('player 1','NY'):30.}
        details={key:{'Projected Minutes':None,'Minutes Source':'Missing'} for key in values}
        uploaded=pd.DataFrame({'Player ID':['1'],'Projection':[0.]})
        result=apply_rotowire_projections(self.pool(),values,details,uploaded)
        self.assertTrue(pd.isna(result.loc[0,'Projected Minutes']))
        self.assertEqual(result.loc[0,'Projection'],25.)
        self.assertTrue(pd.isna(result.loc[1,'Projection']))
        self.assertEqual(result.loc[1,'Projection Source'],'Uploaded CSV')
        self.assertFalse(result.loc[1,'Eligible'])

    def test_injuries_and_uncalibrated_ownership_survive_source_change(self):
        values={('player '+str(i),'NY'):25. for i in range(10)}
        details={key:{'Projected Minutes':30.,'Minutes Source':'RotoWire',
            'RotoWire Projected Own %':50.,'RotoWire Injury':'Active'} for key in values}
        details[('player 0','NY')]['RotoWire Injury']='OUT'
        details[('player 1','NY')]['RotoWire Injury']='Q'
        result=apply_rotowire_projections(self.pool(),values,details)
        self.assertFalse(result.loc[0,'Eligible'])
        self.assertTrue(result.loc[1,'Eligible'])
        self.assertEqual(result.loc[1,'Injury Status'],'Questionable')
        own=field_ownership_inputs(result)
        self.assertEqual(own['mode'],'relative popularity')
        self.assertEqual(own['raw_total'],450.)
        self.assertTrue(result['RotoWire Projected Own %'].eq(50.).all())


if __name__=='__main__':unittest.main()
