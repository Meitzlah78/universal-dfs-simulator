"""Derived diagnostics from passive counters and frozen conditional kernels."""
import hashlib,json
from pathlib import Path
import numpy as np
from scipy.stats import norm
from audit_nfl_fourth_passing_mechanics import load_year
from simmah_nfl_event_levers_offline import fourth_rows,predict_fourth,baseline_fourth,gains,sample_gain
from simmah_nfl_mechanics_audit_offline import ZONES,zone,script

OUT=Path('fourth-passing-audit')

def zone_totals(o,denom):
    rows=[]
    for z in ZONES:
        cells=[c for c in o['fourth_cells'] if c['zone']==z];n=sum(c['opportunities'] for c in cells)
        go=sum(c['opportunities']*(c['go_rate'] or 0) for c in cells)
        rows.append({'zone':z,'opportunities_per_game':n/denom,'go_rate':go/n if n else None,'punts_per_game':sum(c['punts_per_game'] for c in cells),'fg_per_game':sum(c['fg_per_game'] for c in cells)})
    return rows

def main():
    s=json.load(open(OUT/'summary.json'));f,source=load_year(Path('../inputs/Simmah_NFL_PBP_2022-2025_Recovered'),2024)
    policy=json.load(open('../inputs/Simmah_NFL_Event_Levers_Offline_2026-11-14/results/fourth_policy.json'));model=json.load(open('../inputs/Simmah_NFL_Clock_Rebuild_2026-11-14/clock-rebuild/rushing_body_model.json'))
    frozen=json.load(open('late-half-results/frozen_inputs.json'));fourth=fourth_rows(f);p=predict_fourth(policy,fourth);base=baseline_fourth(fourth);z=zone(fourth.yardline_100.to_numpy());sc=script(fourth.game_seconds_remaining.to_numpy(),fourth.score_differential.to_numpy(),fourth.qtr.to_numpy());actual=fourth.play_type.isin(['run','pass']).to_numpy()
    rows=[]
    masks={'all':np.ones(len(fourth),bool),'trailing_any':fourth.score_differential.lt(0).to_numpy(),'late_trailing':sc==0,'end_half':sc==1,'neutral':sc==2,'other':sc==3}
    for i,name in enumerate(ZONES):
        for dist,dm in [('all',np.ones(len(fourth),bool)),('short',fourth.ydstogo.le(2).to_numpy()),('other',fourth.ydstogo.gt(2).to_numpy())]:
            for label,mask in masks.items():
                loc=(z==i)&dm&mask;n=int(loc.sum())
                if n:rows.append({'zone':name,'distance':dist,'script':label,'n':n,'observed_go_rate':float(actual[loc].mean()),'frozen_candidate_expected_go_rate':float(p[loc].mean()),'original_rule_go_rate':float(base[loc].mean())})
    observed=zone_totals(s['observed'],285);sim={a:zone_totals(o,285*1024) for a,o in s['arms'].items()};decomposition=[]
    for o,m in zip(observed,sim['Fourth-Down-Only']):
        actual_rate=o['punts_per_game']/o['opportunities_per_game'];simrate=m['punts_per_game']/m['opportunities_per_game']
        volume=(m['opportunities_per_game']-o['opportunities_per_game'])*actual_rate
        action=m['opportunities_per_game']*(simrate-actual_rate)
        assert abs(volume+action-(m['punts_per_game']-o['punts_per_game']))<1e-9
        decomposition.append({'zone':o['zone'],'observed_punts_per_game':o['punts_per_game'],'simulated_punts_per_game':m['punts_per_game'],'excess':m['punts_per_game']-o['punts_per_game'],'opportunity_volume_and_field_mix':volume,'within_zone_action_mix':action})
    run=gains(f,'run');field=run.yardline_100.to_numpy(float);own=100-field;down=run.down.to_numpy(int);togo=run.ydstogo.to_numpy(float);threshold=np.where(down==1,.4*togo,np.where(down==2,.6*togo,togo));results={name:[] for name in ['gaussian_current','empirical_current','empirical_no_environment_diagnostic','empirical_rounded_diagnostic']}
    for seed in [17311,29107]:
        rng=np.random.default_rng(seed);u=rng.random((len(run),64));env=np.clip(1+rng.normal(0,.1,u.shape),.75,1.3)
        empirical=sample_gain(model,u,env)
        arrays={'gaussian_current':np.clip(norm.ppf(u,loc=frozen['parameters']['rushing_yards'],scale=5.5)*np.sqrt(env),-5,65),
                'empirical_current':empirical,'empirical_no_environment_diagnostic':sample_gain(model,u,np.ones_like(env)),
                'empirical_rounded_diagnostic':np.rint(empirical)}
        for name,g in arrays.items():
            g=np.maximum(np.minimum(g,field[:,None]),-own[:,None]);item={'mean_yards':float(g.mean()),'gain20_rate':float((g>=20).mean()),'by_down':{}}
            for d in [1,2,3,4]:
                mask=down==d
                item['by_down'][str(d)]={'success_rate_yards_only':float((g[mask]>=threshold[mask,None]).mean()),'conversion_rate_yards_only':float((g[mask]>=togo[mask,None]).mean()),'below3_rate':float((g[mask]<3).mean())}
            results[name].append(item)
    sensitivity={}
    for name,items in results.items():
        sensitivity[name]={'mean_yards':float(np.mean([x['mean_yards'] for x in items])),'gain20_rate':float(np.mean([x['gain20_rate'] for x in items])),
            'by_down':{str(d):{k:float(np.mean([x['by_down'][str(d)][k] for x in items])) for k in items[0]['by_down'][str(d)]} for d in [1,2,3,4]}}
    actual_run={'mean_yards':float(run.yards_gained.mean()),'by_down':{}}
    for d in [1,2,3,4]:
        mask=down==d;g=run.yards_gained.to_numpy(float)[mask];actual_run['by_down'][str(d)]={'n':int(mask.sum()),'success_rate_yards_only':float((g>=threshold[mask]).mean()),'conversion_rate_yards_only':float((g>=togo[mask]).mean()),'below3_rate':float((g<3).mean())}
    result={'observed_zone_totals':observed,'simulated_zone_totals':sim,'observed_policy_slices':rows,'punt_decomposition':decomposition,
        'decomposition_scope':'Descriptive identity by coarse field zone; within-zone term includes distance/script mix and is not a causal policy-only effect',
        'conditional_rushing_sensitivity':{'observed':actual_run,'kernels':sensitivity,'scope':'64 shared draws per actual designed-run state, two seeds; yard-only success/conversion excludes fumble logic. No-environment/rounding are diagnostics, not adopted candidates or refits.'},
        'reanchoring_boundary':'4.33906 is observed 2024, not a training target. Saved training body target remains 4.285605594. No calibration change made.',
        '2025':'not opened','production':'unchanged','promotion_gates':'draft','source':source,'reporter_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (OUT/'analysis.json').write_text(json.dumps(result,indent=2));print(json.dumps({'decomposition':decomposition,'run_sensitivity':sensitivity},indent=2))

if __name__=='__main__':main()
