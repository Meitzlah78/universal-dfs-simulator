import unittest
from simmah_nba_blowout_weight_offline import margin_profile,discount_weight,discounted_recent_mean
class BlowoutWeights(unittest.TestCase):
 def event(self,clock,h,a):return {'period':{'number':4},'clock':{'displayValue':clock},'homeScore':h,'awayScore':a}
 def row(self,gid,minutes,day='2026-10-20',completed='2026-10-21T02:00Z'):return {'game_id':gid,'minutes':minutes,'date':day,'completed_at':completed}
 def test_time_weighted_q4_not_event_average(self):
  x=margin_profile([self.event('12:00',80,60),self.event('6:00',100,80),self.event('3:00',100,90),self.event('0:00',110,100)],110,100)
  self.assertEqual(x['q4_last6_mean_abs_margin'],15);self.assertEqual(x['q4_last6_seconds_margin20plus'],180);self.assertEqual(x['final_abs_margin'],10);self.assertEqual(x['quarter_end_home_minus_away']['4'],10)
 def test_nonmonotonic_q4_is_unusable_not_silently_sorted(self):
  x=margin_profile([self.event('12:00',80,60),self.event('5:00',100,80),self.event('6:00',100,80),self.event('0:00',110,100)],110,100);self.assertIsNone(x['q4_last6_mean_abs_margin']);self.assertEqual(discount_weight(x,'q4_hard20'),1);self.assertEqual(x['q4_issue'],'nonmonotonic_q4_source_order')
 def test_hard_and_linear_schemes_separate(self):
  p={'final_abs_margin':30,'q4_last6_mean_abs_margin':15};self.assertEqual(discount_weight(p,'final_hard25'),.5);self.assertEqual(discount_weight(p,'q4_hard20'),1);self.assertEqual(discount_weight(p,'final_linear'),.25);self.assertAlmostEqual(discount_weight(p,'q4_linear'),.8125)
 def test_forecast_cutoff_and_profile_cutoff(self):
  rows=[self.row('1',30),self.row('2',48,'2026-10-30'),self.row('3',48,'2026-10-29','2026-10-31T02:00Z')];profiles={'1':{'final_abs_margin':30,'completed_at':'2026-10-31T02:00Z'}}
  m,n=discounted_recent_mean(rows,'2026-10-30','2026-10-30T22:00Z',5,3,profiles,'final_hard20',10);self.assertEqual(m,30);self.assertEqual(n['n'],1);self.assertEqual(n['missing_profile'],1)
  profiles['1']={'final_abs_margin':40,'completed_at':'2026-10-21T02:00Z','date':'2026-10-30'};m,n=discounted_recent_mean(rows,'2026-10-30','2026-10-30T22:00Z',5,3,profiles,'final_hard20',10);self.assertEqual(m,30);self.assertEqual(n['missing_profile'],1)
 def test_recorded_zero_retains_full_weight(self):
  rows=[self.row('1',0),self.row('2',30)];profiles={g:{'final_abs_margin':40,'completed_at':'2026-10-21T02:00Z'} for g in ['1','2']};m,n=discounted_recent_mean(rows,'2026-10-30','2026-10-30T22:00Z',5,1,profiles,'final_hard20',10);self.assertEqual(m,15);self.assertEqual(n['discounted'],1)
 def test_missing_profile_is_neutral_not_a_zero(self):
  m,n=discounted_recent_mean([self.row('1',30)],'2026-10-30','2026-10-30T22:00Z',5,3,{},'q4_linear',10);self.assertEqual(m,30);self.assertEqual(n['missing_profile'],1)
 def test_window_not_refilled_and_cold_start_unchanged(self):
  rows=[self.row('0',48,'2026-10-19'),self.row('1',20),self.row('2',30)];m,n=discounted_recent_mean(rows,'2026-10-30','2026-10-30T22:00Z',2,1,{},'none',10);self.assertAlmostEqual(m,80/3);self.assertEqual(n['n'],2)
  m,n=discounted_recent_mean([],'2026-10-30','2026-10-30T22:00Z',2,1,{},'none',12);self.assertEqual(m,12);self.assertEqual(n['n'],0)
 def test_invalid_inputs_rejected(self):
  with self.assertRaises(ValueError):discount_weight({'final_abs_margin':10},'unregistered')
  with self.assertRaises(ValueError):margin_profile([],float('nan'),0)
  with self.assertRaises(ValueError):discounted_recent_mean([self.row('1',49)],'2026-10-30','2026-10-30T22:00Z',5,3,{},'none',10)
