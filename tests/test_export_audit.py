import csv
import io
import unittest
from copy import deepcopy

from simmah_export_audit import verify_entry_export


def csv_bytes(rows):
    out=io.StringIO();csv.writer(out).writerows(rows);return out.getvalue().encode()


class ExportAcceptanceTest(unittest.TestCase):
    def fixture(self,site='DraftKings',single=False):
        if single:
            slots=(['CPT']+['FLEX']*5) if site=='DraftKings' else ['MVP - 1.5X Points']+['AnyFLEX']*5
            positions=['QB','RB','WR','TE','K','DST']
        else:
            slots=['QB','RB','RB','WR','WR','WR','TE','FLEX','DST' if site=='DraftKings' else 'DEF']
            positions=['QB','RB','RB','WR','WR','WR','TE','RB','DST']
        contest='222' if site=='DraftKings' else '111-222'
        ids=[str(100+i) if site=='DraftKings' else '111-'+str(100+i) for i in range(len(slots))]
        header=['entry_id','contest_id','contest_name','entry_fee']+slots+['Instructions']
        original=[header,['1',contest,'Míní-Max','.10']+['old']*len(slots)+['Keep me'],
                  ['2',contest,'Míní-Max','.10']+['old']*len(slots)+['Keep me too']]
        exported=deepcopy(original)
        for row in exported[1:]:row[4:4+len(slots)]=ids
        players={p:dict(name='Player '+p,salary=4000,positions={position},team='A' if i%2 else 'B',
                    game='A@B' if i%2 else 'C@D',roster_position='CPT' if single and i==0 else 'FLEX')
                 for i,(p,position) in enumerate(zip(ids,positions))}
        if not single and site=='FanDuel':
            for i,p in enumerate(players.values()):p['team']='ABC'[i%3]
        mode=('Showdown' if single else 'Classic') if site=='DraftKings' else ('Single Game' if single else 'Full Roster')
        return original,exported,players,site,mode

    def check(self,fixture,**kwargs):
        before,after,players,site,mode=fixture
        return verify_entry_export(csv_bytes(before),csv_bytes(after),players,site,mode,**kwargs)

    def test_all_four_formats_and_exact_assignment_round_trip(self):
        for site in ('DraftKings','FanDuel'):
            for single in (True,False):
                f=self.fixture(site,single);end=10 if single else 13
                result=self.check(f,expected_assignments={r[0]:r[4:end] for r in f[1][1:]})
                self.assertTrue(result['passed']);self.assertTrue(result['assignment_parity_verified'])
                self.assertEqual(result['salary_cap'],50000 if site=='DraftKings' else 60000)

    def test_loss_duplicate_extra_id_and_contest_remap_fail(self):
        for mutation in ('missing','duplicate','extra','remap'):
            f=self.fixture();rows=f[1]
            if mutation=='missing':rows.pop()
            if mutation=='duplicate':rows.append(deepcopy(rows[1]))
            if mutation=='extra':rows[-1][0]='9'
            if mutation=='remap':rows[-1][1]='999'
            with self.assertRaises(ValueError,msg=mutation):self.check(f)

    def test_scope_is_explicit_and_unselected_entries_are_reported(self):
        f=self.fixture();f[0][-1][1]='333';f[1].pop()
        result=self.check(f,contest_ids=['222'])
        self.assertEqual(result['excluded_entries'],1)
        with self.assertRaises(ValueError):self.check(f)

    def test_position_salary_same_athlete_and_assignment_corruption_fail(self):
        for corruption in ('position','salary','same-athlete','assignment'):
            f=self.fixture();players=f[2]
            if corruption=='position':players['100']['positions']={'WR'}
            if corruption=='salary':players['100']['salary']=90000
            if corruption=='same-athlete':players['101']['name']=players['100']['name']
            expected={'1':['wrong'],'2':['wrong']} if corruption=='assignment' else None
            with self.assertRaises(ValueError,msg=corruption):self.check(f,expected_assignments=expected)

    def test_fd_60000_cap_and_mvp_salary_multiplier(self):
        f=self.fixture('FanDuel',True)
        for p in f[2].values():p['salary']=9000
        self.assertTrue(self.check(f)['passed'])  # 58,500, legal despite exceeding DK's cap.
        for p in f[2].values():p['salary']=10000
        with self.assertRaisesRegex(ValueError,'salary cap'):self.check(f)

    def test_captain_role_ids_and_cross_slate_fd_ids(self):
        f=self.fixture('DraftKings',True);f[2]['100']['roster_position']='FLEX'
        with self.assertRaisesRegex(ValueError,'wrong slot'):self.check(f)
        f=self.fixture('FanDuel',True);f[1][1][1]='222-333';f[0][1][1]='222-333'
        with self.assertRaisesRegex(ValueError,'another FanDuel slate'):self.check(f)

    def test_instruction_metadata_change_and_original_duplicate_ids_fail(self):
        f=self.fixture();f[1][1][-1]='changed'
        with self.assertRaises(ValueError):self.check(f)
        f=self.fixture();f[0][2][0]='1'
        with self.assertRaises(ValueError):self.check(f)

    def test_dk_roster_only_native_template_can_omit_instruction_footer(self):
        f=self.fixture('DraftKings',True)
        f[0].append(['']*11+['reference'])
        f=list(f);f[1]=[row[:10] for row in f[1]]
        self.assertTrue(self.check(f)['passed'])

    def test_team_and_game_composition(self):
        for site,single in [('DraftKings',False),('FanDuel',False),('DraftKings',True)]:
            f=self.fixture(site,single)
            for p in f[2].values():p['team']='A';p['game']='A@B'
            with self.assertRaises(ValueError):self.check(f)
