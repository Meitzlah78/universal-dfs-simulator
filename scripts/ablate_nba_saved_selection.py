"""Offline selector-only ablation on immutable saved candidate scores."""
import argparse,io,json,zipfile,hashlib,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
from simmah_nba_rules import rules_for
from simmah_nba_portfolio_limits import portfolio_limits,validate_portfolio_limits
from simmah_portfolio_selection import select_portfolio
from simmah_selector_budget import select_quality_budget

def run(directory,output):
 result=[]
 for path in sorted(Path(directory).glob('*Calibration_Solver*.zip')):
  with zipfile.ZipFile(path) as outer:
   data=outer.read('original_build.zip') if 'original_build.zip' in outer.namelist() else path.read_bytes()
  with zipfile.ZipFile(io.BytesIO(data)) as z:
   manifest=json.loads(z.read('manifest.json'))
   for name,info in manifest['files'].items():
    if hashlib.sha256(z.read(name)).hexdigest()!=info['sha256']:raise ValueError('Source hash mismatch '+name)
   meta=json.loads(z.read('inputs/player_pool.json'));pool=pd.DataFrame(meta['rows']);pool.attrs=meta['attrs'];pool['Player ID']=pool['Player ID'].astype(str)
   settings=json.loads(z.read('inputs/settings.json'));slots=list(rules_for(pool)['slots'])
   cand=pd.read_csv(io.BytesIO(z.read('candidate_lineups.csv')),dtype=str);report=pd.read_csv(io.BytesIO(z.read('candidate_scores.csv')))
   saved=pd.read_csv(io.BytesIO(z.read('portfolio_at_build.csv')),dtype={s:str for s in slots})
   rows=report.reset_index(drop=True).copy()
   for s in slots:rows[s]=cand[s]
   metric=settings['rank_metric_at_build'];count=len(saved)
   # Baseline uses the frozen selected roster, not current code applied retrospectively.
   lookup={tuple(sorted(str(v) for v in r)):float(q) for r,q in zip(rows[slots].to_numpy(),rows[metric])}
   baseline=sum(lookup[tuple(sorted(str(v) for v in r))] for r in saved[slots].to_numpy())
   item={'package':path.name,'site':rules_for(pool)['platform'],'date':manifest['slate_date'],'count':count,'metric':metric,'recorded_uncapped':bool(pool.attrs.get('nba_uncapped')),'saved_quality':baseline,'variants':[]}
   variants=[('diversity_zero_recorded_caps',0,False,False),('diversity_25_no_automatic_caps',25,True,False),('diversity_zero_no_automatic_caps',0,True,False),('budget_5pct_recorded_caps',0,False,True)]
   for name,div,uncap,budget in variants:
    p=pool.copy();p.attrs=dict(pool.attrs)
    if uncap:p.attrs['nba_uncapped']=True
    limits=portfolio_limits(p,count=count);start=time.monotonic()
    try:
     selected=select_quality_budget(rows,slots,count,controls=limits,automatic_max=100,quality_metric=metric,time_limit=3.) if budget else select_portfolio(rows,slots,count,metric,controls=limits,diversity=div,automatic_caps=not p.attrs.get('nba_uncapped',False))
     validate_portfolio_limits(selected,slots,limits)
     quality=float(selected[metric].sum());exposure=selected[slots].stack().value_counts()
     item['variants'].append({'name':name,'status':'valid','quality':quality,'quality_change_pct':100*(quality/baseline-1),'maximum_exposure_pct':100*float(exposure.max())/count,'zero_top1_lineups':int(selected['Top 1%'].eq(0).sum()),'metadata':selected.attrs,'seconds':time.monotonic()-start})
    except (ValueError,RuntimeError) as exc:item['variants'].append({'name':name,'status':'failed_explicitly','reason':str(exc),'seconds':time.monotonic()-start})
   result.append(item);Path(output).write_text(json.dumps(result,indent=2,default=str));print(item['site'],item['date'],[(v['name'],v['status'],round(v.get('quality_change_pct',0),1)) for v in item['variants']],flush=True)
 return result
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('directory');a.add_argument('output');v=a.parse_args();run(v.directory,v.output)
