"""Concurrent cold-start history reads with deterministic season ordering."""
from concurrent.futures import ThreadPoolExecutor
import io
import pandas as pd
import requests

SEASONS=(2026,2025,2024,2023)


def download_player_history():
    """Same sources, timeouts, parsing and fallback as the serial loader."""
    def download(season):
        url=f'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.csv'
        try:
            response=requests.get(url,timeout=(4,10))
            response.raise_for_status()
            frame=pd.read_csv(io.BytesIO(response.content),low_memory=False)
            if not frame.empty:
                frame['season']=season
                return frame,None
            return None,None
        except Exception as exc:
            return None,f'{season}: {str(exc)[:120]}'
    frames=[];loaded=[];errors=[]
    # Four independent network waits overlap; completion order never changes
    # the concatenated rows or the historical-role inputs used by simulation.
    with ThreadPoolExecutor(max_workers=len(SEASONS),thread_name_prefix='nfl-history') as executor:
        for season,(frame,error) in zip(SEASONS,executor.map(download,SEASONS)):
            if frame is not None:frames.append(frame);loaded.append(season)
            if error is not None:errors.append(error)
    return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame(),loaded,errors
