import unittest
from scripts.diagnose_core_regression_absence_gaps_offline import classify_raw_gap,raw_athletes
from simmah_nba_history import parse_game
class CoreGapDiagnostics(unittest.TestCase):
 def row(self,**updates):return {'name':'test','team':'BOS','id':'1','minutes':None,'didNotPlay':None,**updates}
 def test_omitted_not_dnp(self):
  reason,rows=classify_raw_gap('test','BOS',[],'1');self.assertEqual(reason,'athlete_omitted_from_source_boxscore');self.assertEqual(rows,[])
 def test_known_positive_and_dnp_evidence(self):
  self.assertEqual(classify_raw_gap('test','BOS',[self.row(minutes=20)],'1')[0],'source_positive_minutes')
  self.assertEqual(classify_raw_gap('test','BOS',[self.row(minutes=0,didNotPlay=True)],'1')[0],'source_explicit_dnp')
 def test_identity_key_gap_requires_same_team_exact_id(self):
  self.assertEqual(classify_raw_gap('test','BOS',[self.row(name='renamed')],'1')[0],'verified_id_name_key_gap')
  self.assertEqual(classify_raw_gap('test','BOS',[self.row(team='NY')],'1')[0],'athlete_found_other_team_only')
 def test_ambiguous_and_zero_without_dnp(self):
  self.assertEqual(classify_raw_gap('test','BOS',[self.row(),self.row(id='2')],'1')[0],'ambiguous_source_identity')
  self.assertEqual(classify_raw_gap('test','BOS',[self.row(minutes=0,didNotPlay=False)],'1')[0],'source_has_no_explicit_participation_or_dnp')
 def test_loader_preserves_boxscore_dnp_fields(self):
  box={'players':[{'team':{'abbreviation':'BOS'},'statistics':[{'labels':['MIN'],'athletes':[{'athlete':{'id':'1','displayName':'Test'},'stats':[],'didNotPlay':True,'reason':'Coach Decision'}]}]}]}
  payload={'header':{'id':'1','competitions':[{'date':'2026-10-20T23:00:00Z','status':{'type':{'completed':True}},'competitors':[{'homeAway':'home','score':'100'},{'homeAway':'away','score':'90'}]}]},'plays':[{'id':'1','homeScore':100,'awayScore':90}],'boxscore':box}
  parsed=parse_game(payload,'1','2026-10-30');self.assertIs(parsed['boxscore'],box);self.assertTrue(parsed['boxscore']['players'][0]['statistics'][0]['athletes'][0]['didNotPlay'])
