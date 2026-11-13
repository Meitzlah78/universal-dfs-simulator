"""Saved-candidate selector integration replay; never rebuild simulations."""
import io,json,sys,zipfile,hashlib,time
from pathlib import Path
import numpy as np
import pandas as pd
from simmah_nba_contest import select_entries
from simmah_nba_portfolio_limits import portfolio_limits,validate_portfolio_limits
from simmah_nba_rules import rules_for

def run(directory,output,part='0/1'):
 k,n=map(int,part.split('/'));records=[]
 for i,path in enumerate(sorted(Path(directory).glob('*Calibration_Solver*.zip'))):
  if i%n!=k:continue
  with zipfile.ZipFile(path) as outer:raw=outer.read('original_build.zip') if 'original_build.zip' in outer.namelist() else path.read_bytes()
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   manifest=json.loads(z.read('manifest.json'))
   for name,info in manifest['files'].items():
    if hashlib.sha256(z.read(name)).hexdigest()!=info['sha256']:raise ValueError('Source hash mismatch '+name)
   m=json.loads(z.read('inputs/player_pool.json'));pool=pd.DataFrame(m['rows']);pool.attrs=m['attrs'];pool['Player ID']=pool['Player ID'].astype(str)
   settings=json.loads(z.read('inputs/settings.json'));slots=list(rules_for(pool)['slots'])
   cand=pd.read_csv(io.BytesIO(z.read('candidate_lineups.csv')),dtype=str);report=pd.read_csv(io.BytesIO(z.read('candidate_scores.csv')));saved=pd.read_csv(io.BytesIO(z.read('portfolio_at_build.csv')),dtype={s:str for s in slots})
  lookup={v:i for i,v in enumerate(pool['Player ID'])};indices=np.array([[lookup[v] for v in row] for row in cand[slots].to_numpy()]);metric=settings['rank_metric_at_build'];count=len(saved)
  qualities={tuple(sorted(v)):float(q) for v,q in zip(cand[slots].to_numpy(),report[metric])};baseline=sum(qualities[tuple(sorted(row))] for row in saved[slots].to_numpy());saved_ex=saved[slots].stack().value_counts()
  limits=portfolio_limits(pool,count=count);baseline_error=None
  try:validate_portfolio_limits(saved,slots,limits)
  except ValueError as e:baseline_error=str(e)
  row={'file':path.name,'site':rules_for(pool)['platform'],'date':manifest['slate_date'],'count':count,'metric':metric,'uncapped':bool(pool.attrs.get('nba_uncapped')),'before_quality':baseline,'before_max_exposure':float(saved_ex.max())*100/count,'before_current_cap_error':baseline_error};start=time.monotonic()
  try:
   chosen=select_entries(pool,indices,report,count,diversity=100,metric=metric);ex=chosen[slots].stack().value_counts();quality=float(chosen[metric].sum());validate_portfolio_limits(chosen,slots,limits)
   row.update(status='valid',after_quality=quality,change_percent=100*(quality/baseline-1),after_max_exposure=float(ex.max())*100/count,zero_top1_lineups=int(chosen['Top 1%'].eq(0).sum()),unique=len({tuple(sorted(v)) for v in chosen[slots].to_numpy()}),cap_violations=0,after_lineups=chosen[slots].astype(str).values.tolist(),metadata=chosen.attrs)
  except (ValueError,RuntimeError) as e:row.update(status='stopped_explicitly',reason=str(e))
  row['seconds']=time.monotonic()-start;records.append(row);Path(output).write_text(json.dumps(records,indent=2,default=str));print(row['site'],row['date'],row['status'],row.get('change_percent'),flush=True)
if __name__=='__main__':run(*sys.argv[1:])
