import unittest
from simmah_nba_rotations import reconstruct_period,audit_rows


def fixture():
    rows=[]
    def add(clock,team,pid,kind,sub=''):
        rows.append(dict(orderNumber=len(rows)+1,period=1,clock=clock,teamId=team,
            personId=pid,actionType=kind,subType=sub,timeActual='2026-04-19T20:00:00Z',gameId='42500001'))
    add('PT12M00S','','','period','start')
    for t,base in [('10',100),('20',200)]:
        for p in range(base,base+5):add('PT11M59S',t,str(p),'2pt')
    for pid,sub in [('100','out'),('101','out'),('105','in'),('106','in')]:add('PT06M00S','10',pid,'substitution',sub)
    add('PT00M00S','','','period','end')
    return rows


class RotationTests(unittest.TestCase):
    def test_joint_swap_and_minutes(self):
        stints,trans=reconstruct_period(fixture())
        self.assertEqual(len(trans),1)
        self.assertEqual(trans[0]['out'],['100','101'])
        self.assertEqual(trans[0]['in'],['105','106'])
        for team in ('10','20'):
            self.assertEqual(sum(x['seconds']*len(x['players']) for x in stints if x['team']==team),3600)
        self.assertTrue(all(len(x['players'])==5 for x in stints))

    def test_duplicate_or_impossible_swap_rejected(self):
        rows=fixture();rows[-2]['personId']='105'
        with self.assertRaises(ValueError):reconstruct_period(rows)

    def test_ambiguous_starters_rejected(self):
        rows=fixture();rows[1]['personId']='999'
        with self.assertRaises(ValueError):reconstruct_period(rows)

    def test_cutoff_and_complete_games(self):
        self.assertEqual(audit_rows(fixture(),'2026-04-19')['source_games'],0)
        r=audit_rows(fixture(),'2026-04-20')
        self.assertEqual(r['accepted_games'],0)
        self.assertIn('Incomplete',r['rejected_games'][0]['reason'])

    def test_full_regulation_and_overtime_conservation(self):
        rows=[]
        for period in range(1,6):
            events=fixture()
            if period==5:
                events[0]['clock']='PT05M00S'
                for e in events[1:-1]:e['clock']='PT04M00S' if e['actionType']!='substitution' else 'PT02M00S'
            for e in events:e['period']=period
            rows.extend(events)
        r=audit_rows(rows,'2026-04-20')
        self.assertEqual(r['accepted_games'],1)
        for team in ('10','20'):
            self.assertEqual(sum(x['seconds']*5 for x in r['stints'] if x['team']==team),265*60)
        self.assertFalse(r['live_enabled'])


if __name__=='__main__':unittest.main()
