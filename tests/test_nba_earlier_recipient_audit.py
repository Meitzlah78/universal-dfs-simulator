import unittest
from scripts.audit_earlier_recipients_offline import convert
class EarlierAudit(unittest.TestCase):
 def game(self):
  teams=[];events=[]
  for team in ['1','2']:
   athletes=[{'athlete':{'id':team+str(i),'displayName':f'Player {team}{i}','position':{'abbreviation':'G'}},'stats':['48'],'didNotPlay':False} for i in range(5)]
   teams.append({'team':{'id':team,'abbreviation':'BOS' if team=='1' else 'NY'},'statistics':[{'labels':['MIN'],'athletes':athletes}]})
  for period in range(1,5):
   for team in ['1','2']:
    for i in range(5):events.append({'period':{'number':period},'clock':{'displayValue':'12:00'},'sequenceNumber':str(999-len(events)),'type':{'text':'Jump Shot'},'shootingPlay':True,'participants':[{'athlete':{'id':team+str(i)}}]})
   events.append({'period':{'number':period},'clock':{'displayValue':'0:00'},'sequenceNumber':'0','type':{'text':'End Quarter'},'participants':[]})
  return {'boxscore':{'players':teams},'events':events}
 def test_source_order_not_sequence_identifier(self):
  _,_,stints,_,error=convert(self.game());self.assertEqual(error,0);self.assertEqual(sum(s['seconds'] for s in stints),5760)
 def test_minute_failure_quarantined(self):
  game=self.game();game['boxscore']['players'][0]['statistics'][0]['athletes'][0]['stats']=['40']
  with self.assertRaisesRegex(ValueError,'minute mismatch'):convert(game)
 def test_unknown_substitution_not_fabricated(self):
  game=self.game();game['events'].insert(0,{'period':{'number':1},'clock':{'displayValue':'12:00'},'type':{'text':'Substitution'},'text':'unknown','participants':[{'athlete':{'id':'999'}}]})
  with self.assertRaisesRegex(ValueError,'identity'):convert(game)
