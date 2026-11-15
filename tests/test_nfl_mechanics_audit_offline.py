import unittest
import numpy as np
from simmah_nfl_mechanics_audit_offline import Observer,zone,script
from simmah_nfl_clock_rebuild_offline import simulate,POLICY_VERSION

class MechanicsAuditTests(unittest.TestCase):
    def test_zone_and_script_boundaries_match_frozen_policy(self):
        np.testing.assert_array_equal(zone(np.array([4.9,5,34.9,35,50,50.1,75,75.1])),[0,1,1,2,2,3,3,4])
        np.testing.assert_array_equal(script(np.array([300,301,1920,1921]),np.array([-1,-1,-20,0]),np.array([4,4,2,2])),[0,2,1,2])
    def test_penalty_proposals_are_not_executed_go_attempts(self):
        o=Observer();o('fourth',{'field':np.array([60.,60.]),'togo':np.array([1.,1.]),'remaining':np.array([1000.,1000.]),'margin':np.array([0.,0.]),'qtr':np.array([3,3]),'go':np.array([True,True]),'executed':np.array([False,True]),'punt':np.array([False,False]),'fg':np.array([False,False])})
        self.assertEqual(o.fourth[:,0].sum(),2);self.assertEqual(o.fourth[:,1].sum(),1);self.assertEqual(o.fourth[:,2].sum(),1)
    def test_passive_counter_identities_and_replay_parity(self):
        clock={'train_years':[2022,2023],'classes':{k:{'ordinary':[35] if k in ['running','early_out_of_bounds'] else [5]} for k in ['running','early_out_of_bounds','late_out_of_bounds','incomplete']}}
        decision={'decision':{'coef':[[0]*34],'intercept':[0]}}
        p=dict(penalty_rate=.07,sack_rate=.065,interception_rate=.02,completion_rate=.64,receiving_yards=11,rushing_yards=4.49,fumble_loss_rate=.006,extra_point_rate=.9468,oob_rate=.12)
        o=Observer();a=simulate(32,12,clock,decision,p,management_policy=POLICY_VERSION,mechanics_trace=o)
        self.assertEqual(a,simulate(32,12,clock,decision,p,management_policy=POLICY_VERSION))
        self.assertEqual(o.dropbacks/32,a['audit']['dropbacks'])
        self.assertEqual(o.play[0,:,0].sum()/32,a['means']['rush_attempts'])
        self.assertEqual(o.play[1,:,0].sum()/32,a['audit']['completions'])
        self.assertEqual(o.fourth[:,0].sum()/32,a['audit']['fourth_opportunities'])
        self.assertEqual(o.fourth[:,3].sum()/32,a['means']['punts'])
        self.assertLessEqual(o.fourth[:,5].sum(),o.fourth[:,2].sum())
