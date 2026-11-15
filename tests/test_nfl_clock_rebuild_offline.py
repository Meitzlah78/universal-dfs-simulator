import unittest
import numpy as np
from simmah_nfl_clock_rebuild_offline import transition,simulate

class ClockRebuildTests(unittest.TestCase):
    def test_quarter_and_zero(self):
        r,e,w=transition([2702,2700,0],[35,35,35])
        np.testing.assert_array_equal(r,[2700,2665,0]);np.testing.assert_array_equal(e,[2,35,0])
    def test_warning_interrupts_only_runoff(self):
        r,e,w=transition([1930,1922],[37,37]);np.testing.assert_array_equal(r,[1920,1885]);self.assertTrue(w.all())
    def test_stopped_has_no_warning_runoff(self):
        r,e,w=transition([1922],[5],stopped=True);self.assertEqual(r[0],1917)
    def test_no_double_live_charge(self):
        r,e,w=transition([3500],[37]);self.assertEqual(e[0],37)
    def test_invalid(self):
        for a,b in [(3601,5),(30,-1),(float('nan'),1)]:
            with self.assertRaises(ValueError):transition(a,b)
    def test_full_game_ledger_and_repeatability(self):
        clock={'train_years':[2022,2023],'classes':{k:{'ordinary':[35] if k in ['running','early_out_of_bounds'] else [5]} for k in ['running','early_out_of_bounds','late_out_of_bounds','incomplete']}}
        decision={'decision':{'coef':[[0]*34],'intercept':[0]}}
        p=dict(penalty_rate=.07,sack_rate=.065,interception_rate=.02,completion_rate=.64,receiving_yards=11,rushing_yards=4.49,fumble_loss_rate=.006,extra_point_rate=.9468,oob_rate=.12)
        a=simulate(16,1,clock,decision,p);b=simulate(16,1,clock,decision,p)
        self.assertEqual(a,b);self.assertEqual(a['ledger_max_error'],0);self.assertAlmostEqual(sum(a['clock_seconds'].values()),3600)
        self.assertGreater(a['means']['snaps'],0)
        m=a['means'];d=a['audit'];e=a['clock_events']
        self.assertEqual(d['dropbacks']+m['rush_attempts'],m['snaps'])
        self.assertEqual(d['completions']+d['incompletions']+d['sacks']+d['interceptions'],d['dropbacks'])
        self.assertEqual(e['penalty'],d['no_play_penalties'])
        self.assertEqual(e['kick'],m['punts']+m['fg_attempts'])
        self.assertEqual(sum(e.values()),m['snaps']+e['kick']+e['penalty'])

if __name__=='__main__':unittest.main()
