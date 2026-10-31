"""Freeze an offline WAS/SF trial from previously downloaded public pages.

No actual results are loaded. This is never imported by the live application.
"""
import sys,json,re,hashlib,argparse
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np,pandas as pd
from lxml import html
from simmah_market_trial import key,parse_covers_pairs,tilt_outcomes
from simmah_matchups import dated_history,matchup_inputs
from simmah_projection_inputs import fit_projection_inputs
from simmah_nfl_engine import simulate_stat_lines
from simmah_nfl_scoring import score_nfl_stat_line
parser=argparse.ArgumentParser()
parser.add_argument('--source-root',default='/tmp')
parser.add_argument('--output',default='data/market_trials/2026-10-19-was-sf')
a=parser.parse_args();src=Path(a.source_root);out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
kickoff='2026-10-20T00:15:00+00:00'
if datetime.now(timezone.utc)>=datetime.fromisoformat(kickoff):raise ValueError('Pregame capture closed')
files=[src/'tonight-dff_dk.html',src/'tonight-dff_fd.html',src/'tonight-draftedge.html',*src.glob('tonight-covers*.html')]
manifest={'trial':'2026-10-19 WAS @ SF','kickoff':kickoff,'frozen_at':datetime.now(timezone.utc).isoformat(),
 'live_app_changed':False,'blend_fraction':.5,'ridge':.05,'min_ess_fraction':.25,'simulation_count_per_platform':10000,
 'source_pages':[{ 'file':p.name,'captured_at':datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files],
 'source_urls':json.loads((src/'tonight-urls.json').read_text())|json.loads((src/'tonight-market-urls.json').read_text()),
 'caveats':['Morning snapshot, not closing lines; individual quote update times unavailable.', 'Provider scoring for generic DraftEdge values not independently confirmed for FanDuel; preserved separately and used exactly as current generic app blend.', 'DFF injury statuses only; Questionable retained. No presumed starters or missing player projections added.', 'Neutral weather; reconstructed dated historical roles.', 'One-sided anytime touchdown prices excluded, no inferred no-vig TD probability.', 'This is a partial-market challenger, not a full market-only point projection model.']}
edge={key(r.get('data-name')):float(r.get('data-proj')) for r in html.fromstring((src/'tonight-draftedge.html').read_bytes()).xpath('//tr[@data-proj]') if r.get('data-team') in {'WAS','SF'} and r.get('data-opp') in {'WAS','SF'}}
pairs=[];rejected=0
for p in files:
 if 'covers' not in p.name:continue
 values,bad=parse_covers_pairs(p.read_bytes());pairs+=values;rejected+=bad
pairs=pd.DataFrame(pairs).drop_duplicates(['Name','Market','Book','Line'])
pairs.to_csv(out/'paired-props.csv',index=False)
manifest['valid_same_book_pairs']=len(pairs);manifest['excluded_rows_including_repeated_cards']=rejected
history=pd.concat([pd.read_csv(src/'matchup-stats2025.csv',low_memory=False),pd.read_csv(src/'matchup-stats2026.csv',low_memory=False)])
schedule=pd.read_csv(src/'matchup-schedule.csv',low_memory=False)
prior=dated_history(history,schedule,kickoff);index={k:v for k,v in prior.groupby(prior.player_display_name.map(key))}
fields={'carries':'carries','targets':'targets','receptions':'receptions','rush_yards':'rushing_yards','rec_yards':'receiving_yards','rush_tds':'rushing_tds','rec_tds':'receiving_tds','pass_attempts':'attempts','completions':'completions','pass_yards':'passing_yards','pass_tds':'passing_tds','interceptions':'passing_interceptions'}
market_stats={'passing_yards':'passing_yards','rushing_yards':'rushing_yards','receiving_yards':'receiving_yards','receptions_made':'receptions','interceptions_thrown':'interceptions'}
outputs=[];fit_reports={};constraint_reports=[];input_snapshots={}
for platform,source in [('DraftKings','dff_dk'),('FanDuel','dff_fd')]:
 rows=[]
 for r in html.fromstring((src/('tonight-'+source+'.html')).read_bytes()).xpath('//tr[contains(@class,"projections-listing")]'):
  if r.get('data-start_date')!='2026-10-19' or {r.get('data-team'),r.get('data-opp')}!={'WAS','SF'}:raise ValueError('Wrong slate')
  dff=float(r.get('data-ppg_proj'));de=edge.get(key(r.get('data-name')))
  projection=float(np.mean([v for v in [dff,de] if v is not None and np.isfinite(v) and v>0])) if dff>0 or (de is not None and de>0) else 0
  rows.append(dict(Name=r.get('data-name'),Team=r.get('data-team'),Opponent=r.get('data-opp'),Position=r.get('data-pos'),Salary=float(r.get('data-salary')),DFF=dff,DraftEdge=de,Projection=projection,**{'Injury Status':r.get('data-inj'),'Weather Kickoff':kickoff}))
 full=pd.DataFrame(rows);full.to_csv(out/(platform.lower()+'-source-projections.csv'),index=False)
 pool=full[full.Projection.gt(0)&~full['Injury Status'].isin(['O','OUT','IR'])].copy()
 roles={}
 for row in pool.itertuples():
  h=index.get(key(row.Name))
  if h is not None and row.Position in {'QB','RB','WR','TE','K'}:
   h=h.sort_values(['season','week']).tail(24)
   roles[row.Name]={o:float(pd.to_numeric(h[c],errors='coerce').fillna(0).clip(lower=0).mean()) for o,c in fields.items()}
 context,report=matchup_inputs(pool,history,schedule)
 for name,v in context.items():roles.setdefault(name,{}).update(v)
 input_snapshots[platform]={'players':json.loads(pool.to_json(orient='records')),'roles':roles,'weather':{},'seed':530001}
 print(platform,'players',len(pool),'fitting baseline',flush=True)
 params,fit=fit_projection_inputs(pool,roles,platform,score_nfl_stat_line,pilot_n=1024,iterations=8)
 stats=simulate_stat_lines(pool,roles,np.random.default_rng(530001),10000,projection_inputs=params,scoring_platform=platform)
 columns=[];targets=[];constraints=[]
 for (name,market),g in pairs.groupby(['Name','Market']):
  actual_name=next((n for n in stats if key(n)==key(name)),None)
  if actual_name is None or market not in market_stats:continue
  # Use one observed threshold per player/stat, most books then closest median.
  choices=g.groupby('Line').Book.nunique();line=sorted(choices.index,key=lambda v:(-choices[v],abs(v-g.Line.median()),v))[0]
  quotes=g[g.Line.eq(line)];target=float(quotes.FairOver.median())
  feature=(stats[actual_name][market_stats[market]]>line).astype(float)
  if feature.min()==feature.max():continue
  columns.append(feature);targets.append(target);constraints.append(dict(Platform=platform,Name=actual_name,Market=market,Line=float(line),Books=int(quotes.Book.nunique()),TargetOver=target,BaselineOver=float(feature.mean())))
 if not columns:raise ValueError('No usable market constraints')
 x=np.column_stack(columns);weights,fit_report=tilt_outcomes(x,targets)
 fit_report.update(players=len(pool),constraints=len(columns));fit_reports[platform]=fit_report
 for c,prob in zip(constraints,x.T@weights):c['FittedOver']=float(prob)
 constraint_reports+=constraints
 for row in pool.itertuples():
  line=stats[row.Name];is_defense=int(row.Position in {'D','DEF','DST'})
  scores=score_nfl_stat_line(dict(line,is_defense=is_defense),platform)
  mean=float(scores.mean());tilted=float(scores@weights)
  challenger=float(row.Projection+.5*(tilted-mean))
  outputs.append(dict(Platform=platform,Name=row.Name,Team=row.Team,Position=row.Position,DFF=row.DFF,DraftEdge=row.DraftEdge,Baseline=row.Projection,BaselineSimMean=mean,MarketWeightedMean=tilted,Experimental=challenger,Change=challenger-row.Projection))
manifest['fit_reports']=fit_reports
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(out/'frozen-inputs.json').write_text(json.dumps(input_snapshots,indent=2,allow_nan=False)+'\n')
pd.DataFrame(outputs).to_csv(out/'frozen-comparison.csv',index=False)
pd.DataFrame(constraint_reports).to_csv(out/'constraints.csv',index=False)
print(json.dumps(fit_reports,indent=2),flush=True)
