import gzip,json,tempfile,unittest
from pathlib import Path
import numpy as np
from simmah_nba_absence_recency_offline import absence_state,tiered_team,transfer_proposal
from scripts.test_fresh_vacancy_recency_offline import load_participation
class AbsenceRecency(unittest.TestCase):
 def calendar(self):return [{'game_id':str(i),'team':'BOS','date':f'2026-10-{20+i}','completed_at':f'2026-10-{21+i}T02:00Z'} for i in range(4)]
 def classify(self,labels,calendar=None):
  p={(str(i),'test','BOS'):s for i,s in enumerate(labels) if s is not None}
  return absence_state(('test','BOS'),self.calendar() if calendar is None else calendar,p,'2026-10-30','2026-10-30T22:00Z')
 def test_three_explicit_misses(self):
  s=self.classify(['played','dnp','dnp','dnp']);self.assertEqual(s['state'],'ongoing_3plus');self.assertEqual(s['consecutive_verified_dnp'],3);self.assertTrue(s['streak_exact'])
 def test_fresh_play_and_one_miss(self):
  self.assertEqual(self.classify(['dnp','dnp','dnp','played'])['state'],'fresh');s=self.classify(['dnp','dnp','played','dnp']);self.assertEqual(s['state'],'fresh');self.assertEqual(s['consecutive_verified_dnp'],1)
 def test_missing_is_unknown_not_zero(self):
  s=self.classify(['played','dnp',None,'dnp']);self.assertEqual(s['state'],'unknown');self.assertEqual(s['consecutive_verified_dnp'],1);self.assertFalse(s['streak_exact'])
 def test_two_missed_transition(self):self.assertEqual(self.classify(['played','played','dnp','dnp'])['state'],'two_missed_transition')
 def test_same_day_and_late_completion_excluded(self):
  c=self.calendar();c[-1]['date']='2026-10-30';self.assertEqual(self.classify(['dnp','dnp','played','dnp'],c)['last3_games'][0],'2')
  c=self.calendar();c[-1]['completed_at']='2026-10-31T02:00Z';self.assertEqual(self.classify(['dnp','dnp','played','dnp'],c)['state'],'fresh')
 def test_duplicate_game_rejected(self):
  with self.assertRaises(ValueError):self.classify(['played']*4,self.calendar()+[self.calendar()[0]])
 def test_minute_zero_without_explicit_dnp_is_unknown(self):
  payload={'event_id':'1','date':'2026-10-20','events':[{'period':{'number':4},'clock':{'displayValue':'0:00'},'wallclock':'2026-10-21T02:00Z'}],'boxscore':{'players':[{'team':{'abbreviation':'BOS'},'statistics':[{'labels':['MIN'],'athletes':[{'athlete':{'displayName':'A'},'stats':['0'],'didNotPlay':False},{'athlete':{'displayName':'B'},'stats':[],'didNotPlay':True},{'athlete':{'displayName':'C'},'stats':['20'],'didNotPlay':True}]}]}]}}
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'2026-10-20';p.mkdir();(p/'1.json.gz').write_bytes(gzip.compress(json.dumps(payload).encode()));_,presence,_=load_participation(tmp)
  self.assertEqual(presence['1','a','BOS'],'unknown');self.assertEqual(presence['1','b','BOS'],'dnp');self.assertEqual(presence['1','c','BOS'],'played')
 def test_independent_tiers_and_budget(self):
  means=[36,34,32,30,28,26,24,16,10,4];roster=[{'name':f'Player {i}','team':'BOS','status':'Active','Projected Minutes':48-m} for i,m in enumerate(means)]
  h=[{'key':('player '+str(i),'BOS'),'minutes':m,'date':f'2026-10-{10+j}','completed_at':f'2026-10-{11+j}T02:00Z','game_id':str(j)} for i,m in enumerate(means) for j in range(10)]
  base,v,tiers=tiered_team(roster,h,'2026-10-30','2026-10-30T22:00Z');self.assertEqual(tiers,['core']*5+['rotation']*2+['bench']*3);self.assertAlmostEqual(v.sum(),240);self.assertTrue(np.all((v>=0)&(v<=48)))
 def test_vacancy_proposal_conserves_and_no_support_is_noop(self):
  v=np.array([36,34,32,30,28,26,24,16,10,4.]);np.testing.assert_array_equal(transfer_proposal(v,np.zeros(10)),v);w=np.zeros(10);w[7:9]=[20,10];x=transfer_proposal(v,w);self.assertAlmostEqual(x.sum(),240);self.assertTrue(np.all((x>=0)&(x<=48)))
