import unittest
from simmah_nba_espn_rotations import reconstruct_rotations
from simmah_nba_rotations import reconstruct_period

class ESPNRotationTests(unittest.TestCase):
 def fixture(self):
  teams=[]
  for team in (1,2):
   teams.append({'team':{'id':str(team)},'statistics':[{'athletes':[{'athlete':{'id':str(team*10+i)},'starter':True} for i in range(5)]}]})
  events=[]
  for period in range(1,5):
   for time in ['12:00','0:00']:
    events.append({'id':str(len(events)),'period':{'number':period},'clock':{'displayValue':time},'type':{'text':'period'}})
   # Later-period starter evidence is contemporaneous play participation.
   if period>1:
    end=events.pop()
    for team in (1,2):
     for i in range(5):events.append({'id':f'{period}-{team}-{i}','period':{'number':period},'clock':{'displayValue':'11:59'},'type':{'text':'jump shot'},'participants':[{'athlete':{'id':str(team*10+i)}}]})
    events.append(end)
  return {'events':events,'boxscore':{'players':teams}}
 def test_explicit_espn_and_cdn_formats_remain_separate(self):
  r=reconstruct_rotations(self.fixture());self.assertTrue(r['complete']);self.assertEqual(sum(r['player_minutes'].values()),480)
 def test_missing_period_and_nonmonotonic_clock_rejected(self):
  g=self.fixture();g['events']=[e for e in g['events'] if e['period']['number']!=3]
  self.assertFalse(reconstruct_rotations(g)['complete'])
  g=self.fixture();g['events'][1]['clock']['displayValue']='1:00'
  self.assertFalse(reconstruct_rotations(g)['complete'])
