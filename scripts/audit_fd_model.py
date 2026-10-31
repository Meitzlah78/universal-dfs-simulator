import sys,time,json,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
parser=argparse.ArgumentParser(description='Offline FD engine diagnostic; not a pregame holdout replay.')
parser.add_argument('--players',required=True)
parser.add_argument('--standings',required=True)
parser.add_argument('--cache-root',required=True)
parser.add_argument('--output',required=True)
parser.add_argument('--roles',help='Frozen pregame role mapping JSON; omitted means explicit model defaults')
parser.add_argument('--weather',help='Frozen pregame weather JSON; omitted means neutral weather')
args=parser.parse_args()
roles=json.loads(Path(args.roles).read_text()) if args.roles else {}
weather=json.loads(Path(args.weather).read_text()) if args.weather else {}
import pandas as pd,numpy as np
from simmah_simulation_store import prepare_simulations
p=pd.read_csv(args.players)
last=[-1]
def progress(f,t):
 step=int(f*10)
 if step>last[0]:print(round(f*100),t,flush=True);last[0]=step
bundle=prepare_simulations(p,roles,'FanDuel',args.cache_root,count=10000,correlation_strength=1.,weather_by_team=weather,progress=progress)
evaluation=bundle['evaluation'];construction=bundle['construction'];fit=bundle['fit_report'];meta=bundle['metadata']
means=evaluation.mean();q=evaluation.quantile([.1,.5,.9,.99]);joined=p.set_index('Name').join(means.rename('mean'));joined['mean_error']=joined['mean']-joined.Projection
actual=pd.read_csv(args.standings,low_memory=False);actual=actual[actual.Player.notna() & actual.FPTS.notna()].copy();actual['Name']=actual.Player.str.replace(r' \(135326-\d+\)$','',regex=True);assert actual.groupby('Name').FPTS.nunique().max()<=1, 'Conflicting actual player scores'
actual=actual.drop_duplicates('Name')
joined=joined.join(actual.set_index('Name').FPTS)
joined=joined.join(q.T.rename(columns={.1:'p10',.5:'p50',.9:'p90',.99:'p99'}))
def summary(g):
 a=g[g.FPTS.notna()]
 return {'players':len(g),'mean_abs_projection_residual':float(g.mean_error.abs().mean()),'max_abs_projection_residual':float(g.mean_error.abs().max()),'matched_actual':len(a),'actual_p10_p90_coverage':float(((a.FPTS>=a.p10)&(a.FPTS<=a.p90)).mean()),'zero_median_players':int((g.p50==0).sum())}
pairs=[]
for team,g in p.groupby('Team'):
 qb=g[g.Position=='QB'].iloc[0].Name
 for receiver in g[g.Position.isin(['WR','TE'])].nlargest(2,'Projection').Name:
  pairs.append({'team':team,'quarterback':qb,'receiver':receiver,'correlation':float(evaluation[qb].corr(evaluation[receiver]))})
report={'scope':'Current engine diagnostic using supplied FD inputs. Role/weather mappings omitted from CLI use model defaults/neutral weather. Not exact original app replay or pregame holdout; not profitability validation. Actual outcomes used only for descriptive comparison after simulation.','simulations_each':len(evaluation),'players':len(p),'finite':bool(np.isfinite(evaluation.to_numpy()).all()),'independent_construction':not evaluation.equals(construction),'overall':summary(joined),'by_position':{pos:summary(g) for pos,g in joined.groupby('Position')},'preparation_key':meta['key'],'qb_receiver_correlations':pairs,'largest_projection_residuals':joined.assign(abs_error=joined.mean_error.abs()).nlargest(12,'abs_error')[['Projection','mean','mean_error','p10','p50','p90']].reset_index().to_dict('records')}
Path(args.output).parent.mkdir(parents=True,exist_ok=True)
open(args.output,'w').write(json.dumps(report,indent=2,default=str)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ['timings','qb_receiver_correlations']},indent=2),flush=True)
