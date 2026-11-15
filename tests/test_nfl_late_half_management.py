import unittest
import numpy as np
from simmah_nfl_clock_rebuild_offline import management_masks, POLICY_VERSION, simulate

class LateHalfPolicyTests(unittest.TestCase):
    def masks(self,r,margin,field=50,normal=True,changed=False,kind='running',timeouts=3):
        return tuple(bool(a[0]) for a in management_masks(*[np.array([x]) for x in (r,margin,field,normal,changed,kind,timeouts)]))
    def test_both_half_boundaries(self):
        for r in [1920,1801,120,1]:self.assertEqual(self.masks(r,7),(True,False))
        for r in [1921,1800,121,0,2700]:self.assertEqual(self.masks(r,7),(False,False))
    def test_timeout_budget_and_terminal_precedence(self):
        self.assertEqual(self.masks(1900,7,timeouts=0),(False,False))
        for kw in [dict(changed=True),dict(normal=False),dict(kind='incomplete'),dict(kind='late_out_of_bounds')]:
            self.assertEqual(self.masks(1900,7,**kw),(False,False))
    def test_hurry_and_margin_limits(self):
        self.assertEqual(self.masks(1900,-7),(False,True))
        self.assertEqual(self.masks(1900,0,field=60),(False,True))
        self.assertEqual(self.masks(1900,0,field=61),(False,False))
        for margin in [-17,17]:self.assertEqual(self.masks(1900,margin),(False,False))
    def test_integrated_ledger_and_timeout_budget(self):
        clock={'train_years':[2022,2023],'classes':{k:{'ordinary':[35] if k in ['running','early_out_of_bounds'] else [5]} for k in ['running','early_out_of_bounds','late_out_of_bounds','incomplete']}}
        decision={'decision':{'coef':[[0]*34],'intercept':[0]}}
        params=dict(penalty_rate=.07,sack_rate=.065,interception_rate=.02,completion_rate=.64,receiving_yards=11,rushing_yards=4.49,fumble_loss_rate=.006,extra_point_rate=.9468,oob_rate=.12)
        result=simulate(128,42,clock,decision,params,management_policy=POLICY_VERSION)
        self.assertEqual(result,simulate(128,42,clock,decision,params,management_policy=POLICY_VERSION))
        self.assertEqual(result['ledger_max_error'],0)
        self.assertAlmostEqual(sum(result['clock_seconds'].values()),3600)
        self.assertEqual(result['means']['snaps'],result['audit']['dropbacks']+result['means']['rush_attempts']+result['means']['kneels'])
        self.assertEqual(result['means']['kneels'],result['late_half']['q4_kneels'])
        for q in [2,4]:
            self.assertLessEqual(result['late_half'][f'q{q}_defensive_timeouts'],6)
            self.assertLessEqual(result['late_half'][f'q{q}_hurry_snaps'],result['late_half'][f'q{q}_snaps'])

class ObservedSliceTests(unittest.TestCase):
    def test_management_and_unambiguous_timeout_context(self):
        import pandas as pd
        from scripts.validate_nfl_late_half import observed_slices
        rows=[]
        for game in ['A','B']:
            rows.append(dict(game_id=game,qtr=2,fixed_drive=1,posteam='H',defteam='V',quarter_seconds_remaining=119,play_type='qb_kneel',qb_kneel=1,qb_spike=0,timeout=0,timeout_team=None,extra_point_attempt=0,two_point_attempt=0))
        rows.append(dict(rows[0],posteam=None,defteam=None,quarter_seconds_remaining=118,play_type='no_play',qb_kneel=0,timeout=1,timeout_team='V'))
        rows.append(dict(rows[0],quarter_seconds_remaining=0,play_type='qb_spike',qb_kneel=0,qb_spike=1))
        f,games,snap,o=observed_slices(pd.DataFrame(rows))
        self.assertEqual(o['q2_snaps']['mean'],1)
        self.assertEqual(o['q2_kneels']['mean'],1)
        self.assertEqual(o['q2_spikes']['mean'],0)
        self.assertEqual(o['q2_defensive_timeouts']['mean'],.5)
        self.assertEqual(o['q2_unclassified_timeouts']['mean'],0)
        self.assertEqual(o['q4_snaps']['mean'],0)

class RevisedManagementTests(unittest.TestCase):
    def test_one_possession_margin_gate(self):
        from simmah_nfl_clock_rebuild_offline import POLICY_VERSION
        for margin,expected in [(0,False),(1,True),(8,True),(9,False),(16,False)]:
            a=management_masks(*[np.array([x]) for x in (1900,margin,50,True,False,'running',3)],policy=POLICY_VERSION)
            self.assertEqual(bool(a[0][0]),expected)
    def test_kneel_clock_down_budget(self):
        from simmah_nfl_clock_rebuild_offline import victory_kneel
        def allowed(r,margin=1,down=1,field=75,tos=0):
            return bool(victory_kneel(*[np.array([x]) for x in (r,margin,down,field,tos)])[0])
        self.assertTrue(allowed(120));self.assertFalse(allowed(121))
        self.assertFalse(allowed(87,tos=1));self.assertTrue(allowed(86,tos=1))
        self.assertFalse(allowed(7,tos=3));self.assertTrue(allowed(6,tos=3))
        self.assertTrue(allowed(42,down=3));self.assertFalse(allowed(43,down=3))
        self.assertFalse(allowed(1,down=4));self.assertFalse(allowed(1,margin=0))
        self.assertFalse(allowed(1,margin=-1));self.assertFalse(allowed(120,field=97))
        self.assertTrue(allowed(120,margin=9,tos=3))
    def test_kneel_sequence_exhausts_time_before_fourth_down(self):
        from simmah_nfl_clock_rebuild_offline import victory_kneel
        for initial in range(1,121):
            for initial_tos in range(4):
                r=initial;tos=initial_tos;down=1
                if not victory_kneel(np.array([r]),np.array([1]),np.array([down]),np.array([75]),np.array([tos]))[0]:continue
                while r>0:
                    self.assertLess(down,4)
                    self.assertTrue(victory_kneel(np.array([r]),np.array([1]),np.array([down]),np.array([75]),np.array([tos]))[0])
                    elapsed=2 if tos>0 else 42
                    r=max(0,r-elapsed);tos=max(0,tos-1);down+=1

class Q2UrgencyTests(unittest.TestCase):
    def masks(self,r=1900,margin=0,field=50,normal=True,changed=False,kind='running',tos=3,defensive=False):
        from simmah_nfl_clock_rebuild_offline import q2_offensive_management
        return tuple(bool(x[0]) for x in q2_offensive_management(*[np.array([x]) for x in (r,margin,field,normal,changed,kind,tos,defensive)]))
    def test_urgency_for_any_trailing_tied_or_sub21_leading_score(self):
        for margin in [-35,-1,0,1,20]:self.assertEqual(self.masks(margin=margin),(True,False))
        self.assertEqual(self.masks(margin=21),(False,False))
        self.assertEqual(self.masks(field=80),(False,False))
        self.assertEqual(self.masks(field=79),(True,False))
    def test_q2_only_and_timeout_clock_budget(self):
        for r in [1921,1800,120,45,1]:self.assertEqual(self.masks(r=r),(False,False))
        self.assertEqual(self.masks(r=1920),(True,False))
        self.assertEqual(self.masks(r=1845),(True,True))
        self.assertEqual(self.masks(r=1846),(True,False))
        self.assertEqual(self.masks(r=1805),(True,False))
        self.assertEqual(self.masks(r=1840,tos=0),(True,False))
    def test_never_double_spend_or_override_stopped_terminal_clock(self):
        for kw in [dict(defensive=True),dict(normal=False),dict(changed=True),dict(kind='incomplete'),dict(kind='late_out_of_bounds'),dict(kind='kick')]:
            self.assertEqual(self.masks(r=1840,**kw),(False,False))
