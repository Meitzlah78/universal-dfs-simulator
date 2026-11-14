import unittest
import numpy as np
from simmah_nba_coupled_minutes_offline import redistribute
from scripts.audit_minutes_scripts_offline import seconds,game_context
class Coupled(unittest.TestCase):
 def test_direction_conservation(self):
  m=np.array([36,34,32,30,28,26,24,16,10,4.])
  for state in ['blowout','tight']:
   x,_=redistribute(m,m,state=state,transfer_budget=12)
   self.assertAlmostEqual(x.sum(),240);self.assertTrue(np.all((x>=0)&(x<=48)))
   self.assertEqual(np.sign(x[7:].sum()-m[7:].sum()),1 if state=='blowout' else -1)
 def test_foul_transfer_and_no_input_mutation(self):
  m=np.full(10,24.);x,_=redistribute(m,m,foul_cuts={0:12})
  self.assertEqual(x[0],12);self.assertAlmostEqual(x.sum(),240);self.assertTrue(np.all(m==24))
 def test_unsupported_and_invalid(self):
  m=np.full(5,48.);x,ledger=redistribute(m,m,state='blowout',transfer_budget=12)
  self.assertEqual(ledger[0]['unallocated'],12)
  with self.assertRaises(ValueError):redistribute([30]*5,[30]*5)
 def test_foul_turnover_not_double_counted(self):
  athlete={'athlete':{'id':'1','displayName':'Test Player'}}
  d={'boxscore':{'players':[{'team':{'abbreviation':'BOS'},'statistics':[{'athletes':[athlete]}]}]},'events':[
   {'period':{'number':1},'type':{'text':t},'participants':[{'athlete':{'id':'1'}}]} for t in ['Offensive Foul','Offensive Foul Turnover','Technical Foul']]}
  ledger,_,_=game_context(d);self.assertEqual(sum(map(len,ledger.values())),1);self.assertEqual(seconds('0:16.9'),16.9)
