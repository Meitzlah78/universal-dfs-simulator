import csv,io,tarfile,tempfile,unittest
from pathlib import Path
from sample_nba_rotations import archive_rows,select_sample,sample_archive

class SeasonSampleTests(unittest.TestCase):
    def test_selection_is_order_independent_and_covers_each_team(self):
        games={'a':{'teams':{'1','2'}},'b':{'teams':{'2','3'}},'c':{'teams':{'3','4'}}}
        chosen=select_sample(games)
        self.assertEqual(chosen,select_sample(dict(reversed(list(games.items())))))
        self.assertEqual(set().union(*(games[g]['teams'] for g in chosen)),{'1','2','3','4'})
        self.assertEqual(select_sample({}),set())

    def archive(self,path,rows,extra=False):
        with tarfile.open(path,'w:xz') as archive:
            buffer=io.StringIO();writer=csv.DictWriter(buffer,fieldnames=['gameId','teamId','timeActual','period'])
            writer.writeheader();writer.writerows(rows);data=buffer.getvalue().encode()
            info=tarfile.TarInfo('../../events.csv');info.size=len(data);archive.addfile(info,io.BytesIO(data))
            if extra:
                info=tarfile.TarInfo('extra.csv');info.size=len(data);archive.addfile(info,io.BytesIO(data))

    def test_cutoff_and_rejections_remain_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'events.tar.xz'
            self.archive(path,[{'gameId':'1','teamId':'10','timeActual':'2024-10-22T00:00:00Z','period':1},
                {'gameId':'2','teamId':'20','timeActual':'2025-07-01T00:00:00Z','period':1}])
            result=sample_archive(path,'2025-07-01')
            self.assertEqual(result['sampling']['archive_games_before_cutoff'],1)
            self.assertEqual(result['sampling']['selected_game_ids'],['1'])
            self.assertEqual(result['accepted_games'],0)
            self.assertEqual(len(result['rejected_games']),1)
            self.assertEqual(len(result['archive_sha256']),64)
            self.assertFalse((Path(tmp).parent/'events.csv').exists())

    def test_multiple_csv_members_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'events.tar.xz';self.archive(path,[],extra=True)
            with self.assertRaises(ValueError):list(archive_rows(path))
