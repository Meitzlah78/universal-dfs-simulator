import csv
import io
import unittest
import pandas as pd
from simmah_exports import build_fanduel_entry_export


class FanDuelExportTest(unittest.TestCase):
    def fixture(self,single=False):
        slots=["MVP","FLEX1","FLEX2","FLEX3","FLEX4","FLEX5"] if single else ["QB","RB1","RB2","WR1","WR2","WR3","TE","FLEX","D"]
        headers=["MVP - 1.5X Points"]+["AnyFLEX"]*5 if single else ["QB","RB","RB","WR","WR","WR","TE","FLEX","DEF"]
        rows=[["entry_id","contest_id","contest_name","entry_fee"]+headers+["Instructions"],
              ["123","111-222","Selected",".25"]+[""]*len(slots)+["keep reference"],
              ["124","111-333","Other",".25"]+["unchanged"]*len(slots)+["other reference"],
              [""]*(4+len(slots))+["remaining reference"]]
        out=io.StringIO(newline="");csv.writer(out,lineterminator="\r\n").writerows(rows)
        portfolio=pd.DataFrame([{s:f"Player {i}" for i,s in enumerate(slots)}])
        ids={f"Player {i}":f"111-{100+i}" for i in range(len(slots))}
        return out.getvalue().encode(),portfolio,ids,rows,slots

    def test_selected_contest_preserves_metadata_and_reference_table(self):
        raw,p,ids,original,slots=self.fixture()
        out,n=build_fanduel_entry_export(raw,p,ids,{"id":"111-222"},"Full Roster")
        rows=list(csv.reader(io.StringIO(out.decode())))
        self.assertEqual(n,1)
        self.assertEqual(rows[0],original[0])
        self.assertEqual(rows[1][:4],original[1][:4])
        self.assertEqual(rows[1][4:13],[ids[p.iloc[0][s]] for s in slots])
        self.assertEqual(rows[1][13:],original[1][13:])
        self.assertEqual(rows[2:],original[3:])
        self.assertNotIn("124",[r[0] for r in rows if r])
        self.assertIn(b"\r\n",out)

    def test_blank_entries_in_other_contests_are_not_uploaded(self):
        raw,p,ids,original,slots=self.fixture()
        original[2][4:4+len(slots)]=[""]*len(slots)
        source=io.StringIO(newline="")
        csv.writer(source).writerows(original)
        out,n=build_fanduel_entry_export(source.getvalue(),p,ids,{"id":"111-222"},"Full Roster")
        rows=list(csv.reader(io.StringIO(out.decode())))
        self.assertEqual(n,1)
        self.assertEqual(rows[1][1],"111-222")
        self.assertTrue(all(rows[1][4:13]))
        self.assertEqual(rows[2:],original[3:])

    def test_single_game_maps_mvp_and_five_flex(self):
        raw,p,ids,_,slots=self.fixture(True)
        out,n=build_fanduel_entry_export(raw,p,ids,{"id":"111-222"},"Single Game")
        rows=list(csv.reader(io.StringIO(out.decode())))
        self.assertEqual(rows[1][4:10],[ids[p.iloc[0][s]] for s in slots])

    def test_blocks_invalid_entry_and_wrong_slate_player(self):
        raw,p,ids,_,_=self.fixture()
        with self.assertRaisesRegex(ValueError,"positive integers"):
            build_fanduel_entry_export(raw.replace(b"123,",b"123.0,"),p,ids,{"id":"111-222"},"Full Roster")
        ids["Player 0"]="999-100"
        with self.assertRaisesRegex(ValueError,"different FanDuel slate"):
            build_fanduel_entry_export(raw,p,ids,{"id":"111-222"},"Full Roster")

    def test_blocks_short_portfolio_and_duplicate_player(self):
        raw,p,ids,_,slots=self.fixture()
        with self.assertRaisesRegex(ValueError,"Need 1"):
            build_fanduel_entry_export(raw,p.iloc[:0],ids,{"id":"111-222"},"Full Roster")
        p.loc[0,slots[1]]=p.loc[0,slots[0]]
        with self.assertRaisesRegex(ValueError,"same player"):
            build_fanduel_entry_export(raw,p,ids,{"id":"111-222"},"Full Roster")


class DirectDownloadTest(unittest.TestCase):
    def test_embedded_bytes_equal_export_and_filename_escaped(self):
        import base64
        import re
        from simmah_exports import direct_csv_download_link
        data = b"entry_id,contest_id,MVP,AnyFLEX\r\n123,111-222,111-1,111-2\r\n"
        html = direct_csv_download_link(data, 'upload"test.csv')
        payload = re.search(r'base64,([^"]+)', html).group(1)
        self.assertEqual(base64.b64decode(payload), data)
        self.assertIn('upload&quot;test.csv', html)

    def test_analysis_report_blocked(self):
        from simmah_exports import direct_csv_download_link
        with self.assertRaises(ValueError):
            direct_csv_download_link(b"MVP,FLEX1,Salary\nA,B,59000", "wrong.csv")
