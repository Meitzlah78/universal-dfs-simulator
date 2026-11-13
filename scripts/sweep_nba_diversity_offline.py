"""Fixed descriptive penalty sweep; no fitted per-slate defaults or promotion."""
import io,json,zipfile,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_portfolio_selection import select_portfolio
from simmah_nba_portfolio_limits import portfolio_limits,validate_portfolio_limits
from simmah_nba_rules import rules_for

def run(evidence,output):
 rows=[]
 for path in sorted(Path(evidence).glob('*Calibration_Solver*.zip')):
  with zipfile.ZipFile(path) as z:raw=z.read('original_build.zip') if 'original_build.zip' in z.namelist() else path.read_bytes()
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   m=json.loads(z.read('inputs/player_pool.json'));settings=json.loads(z.read('inputs/settings.json'));pool=pd.DataFrame(m['rows']);pool.attrs=m['attrs'];pool['Player ID']=pool['Player ID'].astype(str)
   c=pd.read_csv(io.BytesIO(z.read('candidate_lineups.csv')),dtype=str);score=pd.read_csv(io.BytesIO(z.read('candidate_scores.csv')));count=len(pd.read_csv(io.BytesIO(z.read('portfolio_at_build.csv'))))
  slots=list(rules_for(pool)['slots']);c=pd.concat([c[slots].reset_index(drop=True),score.reset_index(drop=True)],axis=1);limits=portfolio_limits(pool,count=count)
  for diversity in [0,5,10,15,25,50]:
   try:
    selected=select_portfolio(c,slots,count,settings['rank_metric_at_build'],controls=limits,diversity=diversity,automatic_caps=not pool.attrs.get('nba_uncapped',False));validate_portfolio_limits(selected,slots,limits)
    ex=selected[slots].stack().value_counts();quality=float(selected[settings['rank_metric_at_build']].sum())
    rows.append({'package':path.name,'uncapped':bool(pool.attrs.get('nba_uncapped')),'diversity':diversity,'quality':quality,'maximum_exposure_pct':100*float(ex.max())/count,'concentration':float((ex**2).sum()),'count':len(selected),'physical_unique':len({tuple(sorted(v)) for v in selected[slots].to_numpy()}),'status':'valid'})
   except (ValueError,RuntimeError) as exc:rows.append({'package':path.name,'uncapped':bool(pool.attrs.get('nba_uncapped')),'diversity':diversity,'status':'failed','reason':str(exc)})
  Path(output).write_text(json.dumps(rows,indent=2));print(path.name,flush=True)
if __name__=='__main__':run(*sys.argv[1:])
