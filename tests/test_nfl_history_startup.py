import ast
import io
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
import pandas as pd
from simmah_nfl_history import SEASONS,download_player_history


class Response:
    def __init__(self,body):self.content=body
    def raise_for_status(self):pass


class HistoryStartupTests(unittest.TestCase):
    def test_four_requests_overlap_and_preserve_serial_data_exactly(self):
        barrier=threading.Barrier(4);calls=[]
        raw={s:f'player_id,targets,season\n{s},3,0\n{s+1},4,0\n'.encode() for s in SEASONS}
        def get(url,timeout):
            season=int(url.rsplit('_',1)[1].split('.')[0]);calls.append((season,timeout))
            barrier.wait(timeout=3)
            return Response(raw[season])
        with patch('simmah_nfl_history.requests.get',side_effect=get):actual,loaded,errors=download_player_history()
        frames=[]
        for season in SEASONS:
            frame=pd.read_csv(io.BytesIO(raw[season]),low_memory=False);frame['season']=season;frames.append(frame)
        pd.testing.assert_frame_equal(actual,pd.concat(frames,ignore_index=True),check_exact=True)
        self.assertEqual(loaded,list(SEASONS));self.assertEqual(errors,[])
        self.assertEqual(sorted(calls),sorted((s,(4,10)) for s in SEASONS))

    def test_partial_failures_and_empty_seasons_keep_fallback_order(self):
        def get(url,timeout):
            if '_2026.' in url:raise OSError('unavailable')
            if '_2025.' in url:return Response(b'player_id,targets\n')
            if '_2024.' in url:raise OSError('other error')
            return Response(b'player_id,targets\nx,3\n')
        with patch('simmah_nfl_history.requests.get',side_effect=get):frame,loaded,errors=download_player_history()
        self.assertEqual(loaded,[2023]);self.assertEqual(frame.season.tolist(),[2023])
        self.assertEqual(errors,['2026: unavailable','2024: other error'])
        with patch('simmah_nfl_history.requests.get',side_effect=OSError('offline')):
            frame,loaded,errors=download_player_history()
        self.assertTrue(frame.empty);self.assertEqual(loaded,[]);self.assertEqual(len(errors),4)

    def test_initial_progress_precedes_history_and_fit(self):
        tree=ast.parse(Path('dfs_app.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='simulate_fd_play_by_play')
        calls=[n for n in ast.walk(fn) if isinstance(n,ast.Call)]
        progress=min(n.lineno for n in calls if isinstance(n.func,ast.Attribute) and n.func.attr=='progress')
        history=next(n.lineno for n in calls if isinstance(n.func,ast.Name) and n.func.id=='load_nfl_historical_player_stats')
        prepare=next(n.lineno for n in calls if isinstance(n.func,ast.Name) and n.func.id=='prepare_simulations')
        self.assertLess(progress,history);self.assertLess(history,prepare)
        loader=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_download_nfl_historical_player_stats')
        self.assertIn('86400',ast.unparse(loader.decorator_list[0]))

if __name__=='__main__':unittest.main()
