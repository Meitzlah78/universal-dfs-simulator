"""Unvalidated, display-only slate-relative summary of independent outcomes."""
import numpy as np
import pandas as pd
from simmah_nba_ownership import active_players
VERSION='simmah-player-display-v1'
WEIGHTS={'Expected points percentile':.40,'P90 percentile':.35,'P90 salary value percentile':.25}

def player_scores(pool,outcomes):
 x=np.asarray(outcomes,float)
 if x.ndim!=2 or x.shape[1]!=len(pool) or not len(x) or not np.isfinite(x).all():raise ValueError('Finite independent outcomes aligned to player pool required')
 salary=pd.to_numeric(pool['Salary'],errors='coerce').to_numpy(float);active=active_players(pool)&np.isfinite(salary)&(salary>0)
 mean=x.mean(axis=0);p90=np.quantile(x,.9,axis=0);p99=np.quantile(x,.99,axis=0);value=np.divide(p90,salary/1000,out=np.full(len(pool),np.nan),where=salary>0)
 r=pool[[c for c in ['Player ID','Name','Team','Opponent','Position','Salary','Projection','Projection Source','Projected Minutes','Minutes Source','Game Total','Team Implied Points','RotoWire Projected Own %','FantasyLabs Projected Own %'] if c in pool]].copy()
 r['Simulated Mean FP']=mean;r['Simulated P90 FP']=p90;r['Simulated P99 FP']=p99
 r['Simulated Hit 5x %']=np.where(active,100*(x>=5*salary[None,:]/1000).mean(axis=0),np.nan)
 score=pd.Series(0.,index=pool.index)
 for label,v in zip(WEIGHTS,[mean,p90,value]):
  ranked=pd.Series(np.nan,index=pool.index);n=int(active.sum())
  if n:ranked.loc[active]=50. if n==1 else 100*(pd.Series(v[active],index=pool.index[active]).rank(method='average')-1)/(n-1)
  r[label]=ranked;score+=WEIGHTS[label]*ranked.fillna(0)
 r['Simmah Score']=score.where(active).round(1)
 for c in pool:
  if c.startswith('DraftDashboard ') and c not in r:r[c]=pool[c]
 r.attrs={'version':VERSION,'status':'experimental unvalidated display heuristic','scope':'relative to active players on this saved site/slate','weights':WEIGHTS,'used_by_selector':False,'input':'independent evaluation fantasy outcomes','provider_ranks_directly_weighted':False}
 return r
