"""Role/direction breakdown of frozen pregame minutes and fantasy intervals."""
import argparse,io,json,sys,zipfile
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.expand_minutes_evidence_offline import player_key,team_key
from scripts.audit_shared_bench_offline import verify_pregame_forecasts


def metrics(f):
    if f.empty:return {'n':0}
    return {'n':len(f),'games':f.game_id.nunique(),'coverage80':float(f.covered.mean()),
        'below_p10':int(f.low80.sum()),'above_p90':int(f.high80.sum()),'outside80':int((~f.covered).sum()),
        'extra_minutes':int((f.delta>5).sum()),'lost_minutes':int((f.delta< -5).sum()),
        'minute_bias_actual_minus_projection':float(f.delta.mean()),'median_minute_error':float(f.delta.median()),
        'verified_dnp':int(f.explicit_dnp.sum()),'PF5plus_proxy':int((f.personal_fouls>=5).sum()),
        'margin20plus_proxy':int((f.final_margin>=20).sum()),'context_missing':int(f.personal_fouls.isna().sum())}


def run(forecasts,evidence,context,output):
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    f=pd.read_csv(forecasts,dtype={'package':str,'game_id':str,'player_id':str});verify_pregame_forecasts(f)
    roles={}
    for path in Path(evidence).rglob('*.zip'):
        with zipfile.ZipFile(path) as z:raw=z.read('original_build.zip') if 'original_build.zip' in z.namelist() else path.read_bytes()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            package=str(json.loads(z.read('inputs/contest.json'))['id']);meta=json.loads(z.read('inputs/player_pool.json'))
        for p in meta['rows']:
            value=p.get('Expected Starter')
            if value not in [True,False,None]:raise ValueError('Unsupported starter flag')
            roles[(package,str(p['Player ID']))]={'expected_starter':value,'snapshot_injury_status':p.get('Injury Status','Unknown')}
    f['expected_starter']=[roles.get((p,i),{}).get('expected_starter') for p,i in zip(f.package,f.player_id)]
    f['snapshot_injury_status']=[roles.get((p,i),{}).get('snapshot_injury_status','Unknown') for p,i in zip(f.package,f.player_id)]
    keys=[player_key(n,t) for n,t in zip(f.name,f.team)];f['name_key']=[k[0] for k in keys];f['team_key']=[k[1] for k in keys]
    c=pd.read_csv(context,dtype={'game_id':str});c['team_key']=c.team_key.map(team_key)
    f=f.merge(c[['game_id','name_key','team_key','personal_fouls','final_margin']],on=['game_id','name_key','team_key'],how='left',validate='many_to_one')
    f['tier']=np.where(f.projected_minutes<18,'bench_lt18',np.where(f.projected_minutes<28,'rotation_18to27','core_ge28'))
    f['delta']=f.actual_minutes-f.projected_minutes;f['large_miss']=f.delta.abs()>5
    f['direction']=np.where(f.delta>5,'extra_minutes',np.where(f.delta< -5,'lost_minutes','within5'))
    f['low80']=f.actual<f.p10;f['high80']=f.actual>f.p90;f['covered']=~(f.low80|f.high80)
    f.to_csv(out/'role_player_rows.csv',index=False)
    result={'live_enabled':False,'source_rows':len(f),'source_packages':f.package.nunique(),'source_games':f.game_id.nunique(),
        'overtime_rows_excluded':int((f.overtimes>0).sum()),'unknown_starter_flags':int(f.expected_starter.isna().sum()),
        'role_definitions':{'starter':'snapshot Expected Starter flag, not retrospectively observed starting lineup',
            'bench':'projected minutes <18','rotation':'18 <= projected minutes <28','core':'projected minutes >=28'},
        'platforms':{},'cautions':['Per-site observations overlap physical games; no independence or significance claim from row counts',
            'Five-plus final fouls and 20-plus final margin are descriptive proxies, not evidence that foul trouble or a blowout caused a minutes miss',
            'No historical injury-update timestamps were recovered, so late-breaking role changes remain unclassified',
            'Regulation-only role results exclude observed OT; old archive model versions vary; production settings and PR77 untouched']}
    for platform,allrows in f[f.overtimes==0].groupby('platform'):
        g=allrows[allrows.large_miss]
        result['platforms'][platform]={'all_nonOT':metrics(allrows),'large_misses':metrics(g),
            'large_misses_by_tier':{str(t):metrics(x) for t,x in g.groupby('tier')},
            'large_misses_by_expected_starter':{str(t):metrics(x) for t,x in g.groupby('expected_starter',dropna=False)},
            'large_misses_by_tier_direction':{str(t)+'/'+str(d):metrics(x) for (t,d),x in g.groupby(['tier','direction'])},
            'all_rows_by_tier':{str(t):metrics(x) for t,x in allrows.groupby('tier')},
            'large_misses_by_saved_minutes_law':{str(v)+'/'+str(w):metrics(x) for (v,w),x in g.groupby(['variable_minutes','wider_minutes'])}}
    (out/'role_summary.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='platforms'},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('forecasts');p.add_argument('evidence');p.add_argument('context');p.add_argument('output');a=p.parse_args();run(a.forecasts,a.evidence,a.context,a.output)
