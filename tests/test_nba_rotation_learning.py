import copy,unittest
from simmah_nba_rotation_learning import fit_rotation_baseline,evaluate_rotation_baseline
class RotationLearningTests(unittest.TestCase):
    def data(self):
        return {'archive_sha256':'fixture','games':[
            {'game_id':'train','date':'2025-01-01','minute_verified':True},
            {'game_id':'later','date':'2025-03-01','minute_verified':True},
            {'game_id':'bad','date':'2025-01-02','minute_verified':False}],
            'units':[{'game_id':g,'team':'A','players':['1','2','3','4','5'],'seconds':100}
                     for g in ['train','later','bad']],
            'transitions':[{'game_id':'train','team':'A','out':['1'],'in':['6'],'count':3},
                           {'game_id':'train','team':'A','out':['1'],'in':['7'],'count':1},
                           {'game_id':'bad','team':'A','out':['1'],'in':['9'],'count':1000},
                           {'game_id':'later','team':'A','out':['1'],'in':['6'],'count':1},
                           {'game_id':'later','team':'A','out':['2'],'in':['8'],'count':1}]}
    def test_no_future_or_unverified_training_and_no_mutation(self):
        d=self.data();snapshot=copy.deepcopy(d)
        m=fit_rotation_baseline(d,'2025-03-01')
        self.assertEqual(m['training_games'],['train'])
        self.assertEqual(sum(r['count'] for r in m['replacements']),4)
        d['transitions'][-1]['count']=999
        self.assertEqual(m,fit_rotation_baseline(d,'2025-03-01'))
        self.assertEqual(snapshot['transitions'][0],d['transitions'][0])
        self.assertFalse(m['live_enabled'])
    def test_probabilities_and_coverage_use_joint_sets(self):
        d=self.data();m=fit_rotation_baseline(d,'2025-03-01')
        self.assertEqual([r['conditional_probability'] for r in m['replacements']],[.75,.25])
        r=evaluate_rotation_baseline(m,d)
        self.assertEqual(r['replacement_events'],2)
        self.assertEqual(r['covered_replacement_events'],1)
        self.assertEqual(r['replacement_coverage'],.5)
        self.assertEqual(r['top1_accuracy_on_covered_events'],1)
        self.assertEqual(r['heldout_games'],1)
    def test_invalid_joint_replacement_and_missing_verification(self):
        d=self.data();d['transitions'][0]['in']=['1']
        with self.assertRaises(ValueError):fit_rotation_baseline(d,'2025-03-01')
        d=self.data()
        for g in d['games']:g['minute_verified']=False
        with self.assertRaises(ValueError):fit_rotation_baseline(d,'2025-03-01')
