"""Passive V5 Fourth-Down-Only/Combined audit; no model refit or 2025 read."""
import hashlib,json,sys
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np
import pandas as pd
from simmah_nfl_clock_rebuild_offline import simulate,POLICY_VERSION
from simmah_nfl_mechanics_audit_offline import Observer,ZONES,SCRIPTS,FOURTH_COLS,PLAY_COLS
from simmah_nfl_event_levers_offline import COLUMNS,common,fourth_rows,predict_fourth,baseline_fourth,evaluate_gains,gains

OUT=Path('fourth-passing-audit');ROOT=Path('..');CONFIG=None
ARMS=['Fourth-Down-Only','Combined']

def init(config):
    global CONFIG
    CONFIG=config

def replay(path):
    row=json.loads(Path(path).read_text());game=row['game_id'];result={}
    for arm in ARMS:
        observer=Observer();batches=[]
        for slot,seed in enumerate([17311,29107]):
            key=int(hashlib.sha256(f'{game}|{seed}'.encode()).hexdigest()[:16],16)
            kw={'fourth_policy':CONFIG['fourth'],'management_policy':POLICY_VERSION,'mechanics_trace':observer}
            if arm=='Combined':kw['run_model']=CONFIG['run']
            batch=simulate(512,key,CONFIG['clock'],CONFIG['decision'],CONFIG['parameters'],**kw)
            if batch!=row['arms'][arm][slot]:raise ValueError('Passive instrumentation changed arm output: '+game+' '+arm)
            batches.append(batch)
        result[arm]=observer.result()
    (OUT/'games'/Path(path).name).write_text(json.dumps({'game_id':game,'arms':result}))
    return result

def load_year(root,year):
    if year not in [2022,2023,2024]:raise ValueError('Locked year')
    path=root/f'play_by_play_{year}.csv.gz'
    f=pd.read_csv(path,usecols=list(dict.fromkeys(COLUMNS+['fumble_lost','sack','interception'])),low_memory=False)
    if set(f.season.dropna().astype(int))!={year} or f.duplicated(['game_id','play_id']).any():raise ValueError('Invalid PBP')
    return f,{'file':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def observed(f,policy):
    o=Observer();fourth=fourth_rows(f)
    d={'field':fourth.yardline_100.to_numpy(float),'togo':fourth.ydstogo.to_numpy(float),'remaining':fourth.game_seconds_remaining.to_numpy(float),'margin':fourth.score_differential.to_numpy(float),'qtr':fourth.qtr.to_numpy(int),
       'go':fourth.play_type.isin(['run','pass']).to_numpy(),'executed':np.ones(len(fourth),bool),'punt':fourth.play_type.eq('punt').to_numpy(),'fg':fourth.play_type.eq('field_goal').to_numpy(),
       'candidate_expected_go':predict_fourth(policy,fourth),'baseline_expected_go':baseline_fourth(fourth)}
    o('fourth',d)
    plays=f.loc[common(f)&f.down.between(1,4)&f.ydstogo.between(0,100)&f.game_seconds_remaining.between(0,3600)&f.play_type.isin(['run','pass'])&f.yards_gained.between(-99,100)].copy()
    gain=plays.yards_gained.to_numpy(float);turn=plays.fumble_lost.eq(1).to_numpy()|plays.interception.eq(1).to_numpy()
    o('play',{'field':plays.yardline_100.to_numpy(float),'togo':plays.ydstogo.to_numpy(float),'remaining':plays.game_seconds_remaining.to_numpy(float),'margin':plays.score_differential.fillna(0).to_numpy(float),'qtr':plays.qtr.to_numpy(int),'down':plays.down.to_numpy(int),
      'gain':gain,'passing':plays.play_type.eq('pass').to_numpy(),'caught':plays.play_type.eq('pass').to_numpy()&plays.complete_pass.eq(1).to_numpy(),'running':plays.play_type.eq('run').to_numpy()&plays.qb_scramble.eq(0).to_numpy(),
      'turnover':turn,'td':(plays.rush_touchdown.eq(1)|plays.pass_touchdown.eq(1)).to_numpy(),'conversion':(gain>=plays.ydstogo.to_numpy(float))&~turn})
    return o

def summarize(o,denom):
    arr=o['fourth'];plays=o['play'];rows=[]
    for zone,zname in enumerate(ZONES):
        for short in [0,1]:
            for script,sname in enumerate(SCRIPTS):
                v=arr[(zone*2+short)*4+script];n=v[1]
                rows.append({'zone':zname,'distance':'short' if short==0 else 'other','script':sname,'opportunities':float(n),'opps_per_game':float(n/denom),'go_rate':float(v[2]/n) if n else None,'punts_per_game':float(v[3]/denom),'fg_per_game':float(v[4]/denom),'conversions_per_go':float(v[5]/v[2]) if v[2] else None,'candidate_expected_go_rate':float(v[6]/n) if n and v[6]>0 else None})
    totals={}
    for k,name in enumerate(['designed_run','completion']):
        total=plays[k].sum(axis=0);n=total[0]
        totals[name]={c:float(v) for c,v in zip(PLAY_COLS,total)}
        totals[name].update({'per_game':float(n/denom),'mean_yards':float(total[1]/n),'gain20_rate':float(total[2]/n),'gain40_rate':float(total[3]/n),'gain20_field_eligible_rate':float(total[2]/total[4]),'gain40_field_eligible_rate':float(total[3]/total[5]),'success_rate':float(total[8]/n),'nonpositive_rate':float(total[9]/n)})
        totals[name]['by_down']={}
        for down in [1,2,3,4]:
            t=plays[k,(down-1)*3:down*3].sum(axis=0)
            totals[name]['by_down'][str(down)]={'n':float(t[0]),'mean_yards':float(t[1]/t[0]) if t[0] else None,'success_rate':float(t[8]/t[0]) if t[0] else None,'nonpositive_rate':float(t[9]/t[0]) if t[0] else None,'below3_rate':float(t[10]/t[0]) if t[0] else None}
    totals['pass_plays_including_sacks_excluding_scrambles']=float(o['dropbacks'])
    totals['gain40_per_pass_play']=float(totals['completion']['g40']/o['dropbacks'])
    return {'fourth_cells':rows,'play_totals':totals}

def main():
    OUT.mkdir(exist_ok=True);(OUT/'games').mkdir(exist_ok=True)
    config=json.load(open('late-half-results/frozen_inputs.json'));config['fourth']=json.load(open('../inputs/Simmah_NFL_Event_Levers_Offline_2026-11-14/results/fourth_policy.json'));config['run']=json.load(open('../inputs/Simmah_NFL_Clock_Rebuild_2026-11-14/clock-rebuild/rushing_body_model.json'))
    paths=sorted(Path('four-arm-v5-results/games').glob('2024_*.json'))
    if len(paths)!=285 or POLICY_VERSION!='late-half-management-v5':raise ValueError('Frozen 285-game V5 only')
    totals={a:{'fourth':np.zeros((40,len(FOURTH_COLS))),'play':np.zeros((2,12,len(PLAY_COLS))),'dropbacks':0} for a in ARMS}
    count=0
    if '--summarize-only' in sys.argv:
        for p in paths:
            for arm,values in json.loads((OUT/'games'/p.name).read_text())['arms'].items():
                for key in ['fourth','play']:totals[arm][key]+=np.asarray(values[key])
                totals[arm]['dropbacks']+=values['dropbacks']
    else:
        with ProcessPoolExecutor(max_workers=4,initializer=init,initargs=(config,)) as pool:
            for future in as_completed([pool.submit(replay,str(p)) for p in paths]):
                for a,values in future.result().items():
                    for key in ['fourth','play']:totals[a][key]+=np.asarray(values[key])
                    totals[a]['dropbacks']+=values['dropbacks']
                count+=1
                if count%25==0:print(f'Matched mechanics audit {count}/285',flush=True)
    root=ROOT/'inputs/Simmah_NFL_PBP_2022-2025_Recovered';f,source=load_year(root,2024);obs=observed(f,config['fourth']);sources=[source]
    result={'scope':'Passive matched 285-game replay of Fourth-Down-Only and Combined; every output dictionary matches all 1140 saved arm batches exactly; observed 2024 is reused development data',
        'simulated_trials_per_arm':285*1024,'observed_games':int(f.game_id.nunique()),'arms':{a:summarize(v,285*1024) for a,v in totals.items()},'observed':summarize({'fourth':obs.fourth,'play':obs.play,'dropbacks':obs.dropbacks},285),
        'observed_regulation_punts_per_game':float((f.qtr.between(1,4)&f.play_type.eq('punt')).sum()/285),'rushing_training':{},'2025':'not opened','production':'unchanged','promotion_gates':'draft'}
    for year in [2022,2023]:
        frame,source=load_year(root,year);sources.append(source);g=gains(frame,'run');result['rushing_training'][str(year)]={'n':len(g),'sum_yards':float(g.yards_gained.sum()),'mean':float(g.yards_gained.mean())}
    t=result['rushing_training'];result['rushing_training']['pooled_mean']=sum(t[str(y)]['sum_yards'] for y in [2022,2023])/sum(t[str(y)]['n'] for y in [2022,2023])
    result['rushing_training']['saved_body_fit']=config['run']['body_calibration']
    models=json.load(open('../inputs/Simmah_NFL_Event_Levers_Offline_2026-11-14/results/gain_models.json'));models['run']=config['run']
    conditional=evaluate_gains(models,f,draws=64);(OUT/'conditional_gains.json').write_text(json.dumps(conditional,indent=2))
    result['sources']=sources;result['source_sha256']={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in ['simmah_nfl_clock_rebuild_offline.py','simmah_nfl_mechanics_audit_offline.py',__file__]}
    (OUT/'summary.json').write_text(json.dumps(result,indent=2));print('Completed matched mechanics audit and conditional gain checks',flush=True)

if __name__=='__main__':main()
