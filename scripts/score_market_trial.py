"""Grade a frozen trial from final weekly NFL raw statistics, never refit it."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
from simmah_market_trial import key
from simmah_nfl_scoring import score_nfl_stat_line

def grade(trial,weekly,game_id='2026_06_WAS_SF'):
    actual=weekly[weekly.game_id.eq(game_id)].copy()
    if actual.empty:raise ValueError('Final game statistics not available; do not grade as zeros')
    lookup={key(name):g for name,g in actual.groupby('player_display_name')}
    scored=[];excluded=[]
    fields={'passing_yards':'passing_yards','passing_tds':'passing_tds','interceptions':'passing_interceptions',
            'rushing_yards':'rushing_yards','rushing_tds':'rushing_tds','receiving_yards':'receiving_yards',
            'receiving_tds':'receiving_tds','receptions':'receptions'}
    for row in trial.itertuples():
        if row.Position in {'D','DEF','DST'}:
            excluded.append({'Platform':row.Platform,'Name':row.Name,'reason':'DST requires verified contest score; not inferred from final team scores'})
            continue
        g=lookup.get(key(row.Name))
        if g is None or len(g)!=1:
            excluded.append({'Platform':row.Platform,'Name':row.Name,'reason':'Missing or ambiguous actual record'})
            continue
        r=g.iloc[0];stats={out:float(r[col]) for out,col in fields.items()}
        stats['fumbles_lost']=sum(float(r[c]) for c in ['sack_fumbles_lost','rushing_fumbles_lost','receiving_fumbles_lost'])
        stats['two_point_conversions']=sum(float(r[c]) for c in ['passing_2pt_conversions','rushing_2pt_conversions','receiving_2pt_conversions'])
        if row.Position=='K':
            stats.update(fg_under_40=sum(float(r[c]) for c in ['fg_made_0_19','fg_made_20_29','fg_made_30_39']),
                         fg_40_49=float(r.fg_made_40_49),fg_50_plus=float(r.fg_made_50_59)+float(r.fg_made_60_),extra_points_made=float(r.pat_made))
        value=float(score_nfl_stat_line(stats,row.Platform))
        scored.append(dict(Platform=row.Platform,Name=row.Name,Position=row.Position,Actual=value,
            Baseline=row.Baseline,Experimental=row.Experimental,BaselineError=abs(row.Baseline-value),ExperimentalError=abs(row.Experimental-value)))
    detail=pd.DataFrame(scored)
    if detail.empty:raise ValueError('No verifiable player scores')
    report={'game_id':game_id,'scope':'Frozen morning point-projection test. No lineup/ROI validation. DST excluded unless separately supplied with verified contest actuals.',
        'by_platform':{site:{'players':len(g),'baseline_mae':float(g.BaselineError.mean()),'experimental_mae':float(g.ExperimentalError.mean()),'players_with_lower_error':int((g.ExperimentalError<g.BaselineError).sum())} for site,g in detail.groupby('Platform')},'excluded':excluded,'players':detail.to_dict('records')}
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--trial',required=True);p.add_argument('--weekly',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    result=grade(pd.read_csv(a.trial),pd.read_csv(a.weekly,low_memory=False))
    Path(a.output).write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print(json.dumps(result['by_platform'],indent=2))
