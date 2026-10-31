import json,unittest
from simmah_nba_boxscore_pages import parse_boxscore_page
class OfficialPageTests(unittest.TestCase):
 def page(self,status=3,gid='0042500101',minute='25:28',comment=''):
  game={'gameId':gid,'gameStatus':status,'homeTeam':{'players':[{'statistics':{'minutes':minute},'comment':comment}]},'awayTeam':{'players':[]}}
  return '<script id="__NEXT_DATA__" type="application/json">'+json.dumps({'props':{'pageProps':{'game':game}}})+'</script>'
 def test_minutes_and_explicit_dnp(self):
  x=parse_boxscore_page(self.page(),'0042500101');self.assertEqual(x['game']['homeTeam']['players'][0]['statistics']['minutes'],'PT25M28.0S')
  x=parse_boxscore_page(self.page(minute='',comment="DNP - Coach\'s Decision"),'0042500101');self.assertEqual(x['game']['homeTeam']['players'][0]['played'],'0')
 def test_unknown_minutes_not_zero(self):
  x=parse_boxscore_page(self.page(minute=''),'0042500101');self.assertNotIn('played',x['game']['homeTeam']['players'][0])
 def test_display_rounding_and_dnd(self):
  x=parse_boxscore_page(self.page(minute='28:60'),'0042500101');self.assertEqual(x['game']['homeTeam']['players'][0]['statistics']['minutes'],'PT29M0.0S')
  x=parse_boxscore_page(self.page(minute='',comment='DND - Injury/Illness'),'0042500101');self.assertEqual(x['game']['homeTeam']['players'][0]['played'],'0')
 def test_final_identity_and_bad_format_guards(self):
  for html,gid in [(self.page(status=2),'0042500101'),(self.page(),'0042500102'),(self.page(minute='25:99'),'0042500101'),(self.page(),'../../x')]:
   with self.assertRaises(ValueError):parse_boxscore_page(html,gid)

 def test_explicit_nwt_is_zero_but_unexplained_absence_is_not(self):
  for comment in ['NWT - Injury/Illness','NWT - Not With Team']:
   x=parse_boxscore_page(self.page(minute='',comment=comment),'0042500101')
   self.assertEqual(x['game']['homeTeam']['players'][0]['played'],'0')
  x=parse_boxscore_page(self.page(minute='',comment='unknown'),'0042500101')
  self.assertNotIn('played',x['game']['homeTeam']['players'][0])
