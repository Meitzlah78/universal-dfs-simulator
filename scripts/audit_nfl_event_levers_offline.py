"""Fit 2022/23 candidates; 2024 conditional diagnostics only. No 2025 reads."""
import argparse,json
from pathlib import Path
import pandas as pd
from simmah_nfl_event_levers_offline import read_season,fit_gain,fit_fourth,evaluate_gains,evaluate_fourth,VERSION


def run(data,out,draws):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);frames=[];sources=[]
    for year in [2022,2023,2024]:
        f,source=read_season(data,year);frames.append(f);sources.append(source)
    train=pd.concat(frames[:2],ignore_index=True);test=frames[2]
    models={kind:fit_gain(train,kind) for kind in ['run','completion']};policy=fit_fourth(train)
    (out/'gain_models.json').write_text(json.dumps(models));(out/'fourth_policy.json').write_text(json.dumps(policy,indent=2))
    tail=evaluate_gains(models,test,draws=draws);fourth=evaluate_fourth(policy,test)
    (out/'gain_diagnostics_2024.json').write_text(json.dumps(tail,indent=2));(out/'fourth_diagnostics_2024.json').write_text(json.dumps(fourth,indent=2))
    manifest={'version':VERSION,'source_files_opened':sources,'fit_seasons':[2022,2023],'evaluation_season':2024,
        'games':int(test.game_id.nunique()),'2025':'not opened','production':'unchanged','kickoffs':'unchanged',
        'full_game_ablation':'blocked: corrected-clock replay source not retained in recovered checkpoints',
        'promotion':'not ready; conditional mechanics evidence only, gates remain draft'}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps({'gains':{k:{'latent_mean':v['latent_mean'],'records':v['records'],'censored':v['censored_touchdowns']} for k,v in models.items()},
        'fourth':{k:v for k,v in fourth.items() if k!='slices'},'games':manifest['games']}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('data');p.add_argument('out');p.add_argument('--draws',type=int,default=64);a=p.parse_args();run(a.data,a.out,a.draws)
