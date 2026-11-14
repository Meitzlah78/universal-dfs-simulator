"""Fresh same-engine paired fantasy replay for chronological minute folds."""
import argparse,json,sys,time
from pathlib import Path
from unittest.mock import patch
import numpy as np,pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.fit_coupled_minutes_offline import load_archive,sampler
from simmah_nba_pregame import PregameEngine

def run(root,trials,package_filter=None):
    root=Path(root);out=root/'minutes-coupled-cv';models=json.loads((out/'folds.json').read_text())
    f=pd.read_csv(root/'minutes-script-results/all_forecasts_context.csv',dtype={'game_id':str,'package':str,'player_id':str});f=f[f.overtimes==0]
    for path in sorted((root/'minutes-expanded-evidence').glob('*.zip')):
        pool,c,markets,rates=load_archive(path);date=c['date'];package=str(c['id'])
        if date not in models or (package_filter and package!=package_filter):continue
        pool.attrs['nba_variable_minutes']=True;pool.attrs['nba_wider_minutes']=True
        obs=f[f.package==package];index={str(p):i for i,p in enumerate(pool['Player ID'])}
        for arm in ['independent','coupled']:
            target=out/(package+'_'+arm+'_fp.csv')
            if target.exists():continue
            start=time.perf_counter();engine=PregameEngine(pool,markets,rates,platform=c['platform'],parallel=False)
            with patch('simmah_nba_pregame.draw_wider_minutes',sampler(models[date],arm)):
                engine(1024,83);draws=engine(trials,2100)
            rows=[]
            for r in obs.itertuples():
                i=index[str(r.player_id)];lo,hi=np.quantile(draws[:,i],[.1,.9]);rows.append({'package':package,'date':date,'platform':c['platform'],'game_id':r.game_id,'team':r.team_key,'name':r.name_key,'tier':r.tier,'large_miss':abs(r.delta)>5,'actual':r.actual,'p10':float(lo),'p90':float(hi),'covered':bool(lo<=r.actual<=hi),'mean':float(draws[:,i].mean()),'projection':r.source_projection})
            pd.DataFrame(rows).to_csv(target,index=False)
            (out/(package+'_'+arm+'_report.json')).write_text(json.dumps({'arm':arm,'seconds':time.perf_counter()-start,'trials':trials,'reports':engine.last_report},default=str,indent=2))
            print(package,arm,round(time.perf_counter()-start,1),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('--trials',type=int,default=2000);p.add_argument('--package');a=p.parse_args();run(a.root,a.trials,a.package)
