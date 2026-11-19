import csv
import io
import unittest
import pandas as pd
import test_nba_rosters
from test_nba_draftkings import template
from simmah_nba_import import read_template
from simmah_nba_rosters import export_entries, isolate_contest_entries
from simmah_nba_late_swap import swap_entries, export_swaps


def encode(rows):
    out=io.StringIO(newline='');csv.writer(out,lineterminator='\r\n').writerows(rows)
    return out.getvalue().encode()


class ExportIsolationTests(unittest.TestCase):
    def test_both_sites_compact_selected_entries_preserve_reference_cells(self):
        for size,cid_col in [(9,1),(8,2)]:
            def row(e,c,ids):
                meta=[e,c,'contest','.05'] if cid_col==1 else [e,'contest',c,'.10']
                return meta+ids+['reference '+e]
            rows=[['header']*(5+size),row('1','free',['']*size),
                  row('2','paid',['p']*size),row('3','other',['q']*size)]
            original=[r.copy() for r in rows]
            isolate_contest_entries(rows,'paid',size,cid_col)
            self.assertEqual(rows[1][:4+size],original[2][:4+size])
            self.assertTrue(all(not any(r[:4+size]) for r in rows[2:]))
            self.assertEqual([r[4+size:] for r in rows],[r[4+size:] for r in original])
            self.assertEqual(rows[0],original[0])

    def test_fanduel_blank_free_entry_cannot_leak_into_paid_export(self):
        fixture=test_nba_rosters.NBARosterTests();fixture.setUp();pool=fixture.pool;ids=fixture.ids
        rows=[['entry_id','contest_id','contest_name','entry_fee','PG','SG','SF','PF','C','G/F','F/C','UTIL','UTIL','','Instructions'],
              ['1','42-98','free','0']+['']*9+['','keep instructions'],
              ['2','42-99','paid','.05']+['']*9+['','Id','Nickname','Salary','Position','Team','Opponent','Game','Injury Indicator','Injury Details','FPPG']]
        for r in pool.to_dict('records'):
            rows.append(['']*14+[r['Player ID'],r['Name'],str(r['Salary']),r['Position'],r['Team'],r['Opponent'],r['Game'],'','','30'])
        source=encode(rows)
        out=export_entries(source,[ids],'42-99',pool,salary_cap=60000,max_from_team=4)
        parsed=read_template(out)
        self.assertEqual([(r[0],r[1]) for r in parsed['entries']],[('2','42-99')])
        self.assertEqual(parsed['entries'][0][4:13],ids)
        pd.testing.assert_frame_equal(parsed['players'],read_template(source)['players'])
        after=list(csv.reader(io.StringIO(out.decode())))
        self.assertEqual([r[13:] for r in after],[r[13:] for r in rows])
        self.assertEqual(source,encode(rows))

    def test_draftkings_and_late_swap_also_omit_foreign_entries(self):
        source=template();rows=list(csv.reader(io.StringIO(source.decode())))
        rows.insert(1,['999','Free contest','free','$0']+['']*8+['','keep'])
        mixed=encode(rows);pool=read_template(mixed)['players'];pool['Projection']=30.;pool['Eligible']=True
        from simmah_nba_candidates import build_candidates
        import numpy as np
        candidates=build_candidates(pool,np.ones((5,len(pool))),target=3)
        lineups=[pool.iloc[x]['Player ID'].tolist() for x in candidates['indices'][:3]]
        filled=export_entries(mixed,lineups,'196711762',pool,salary_cap=50000,max_from_team=8)
        self.assertEqual(len(read_template(filled)['entries']),3)
        # Add a foreign blank again to exercise the separate late-swap exporter.
        rows=list(csv.reader(io.StringIO(filled.decode())))
        rows.insert(1,['999','Free contest','free','$0']+['']*8+['','keep'])
        current=encode(rows);now=pd.Timestamp('2026-10-21T00:00:00Z')
        swaps=swap_entries(current,'196711762',pool,now=now,seconds=2)
        output=export_swaps(current,'196711762',pool,swaps,now=now)
        entries=read_template(output,game_context_pool=pool)['entries']
        self.assertEqual(len(entries),3)
        self.assertTrue(all(r[1]=='196711762' for r in entries))
        self.assertEqual([r[:4] for r in entries],[r[:4] for r in read_template(filled)['entries']])


if __name__=='__main__':unittest.main()
