import pandas as pd,numpy as np,re,zipfile,itertools,hashlib,json
from pathlib import Path
import sys
root=Path(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
files=['Simmah_NBA_DraftKings_Build_Player_Pool (1).csv','contest-standings-196983215.zip','Simmah_NBA_Opponent_Field.csv','Simmah_NBA_Opponent_Field (1)(1).csv','Simmah_NBA_FanDuel_Build_Player_Pool.csv','135636-281187909.csv','Simmah_NBA_Opponent_Field (2)(2).csv']
p=pd.read_csv(root/files[0]);nm=p.set_index('Name')['Player ID'];rev=p.set_index('Player ID').Name;salary=p.set_index('Player ID').Salary;slots=['PG','SG','SF','PF','C','G','F','UTIL'];z=zipfile.ZipFile(root/files[1]);d=pd.read_csv(z.open(z.namelist()[0]));rows=[]
for s in d.Lineup.dropna():
 a=[x.strip() for x in re.split(r'(?:^|\s)(PG|SG|SF|PF|C|G|F|UTIL)\s',s)[2::2]]
 if len(a)==8 and len(set(a))==8:rows.append([nm[x] for x in a])
a=np.array(rows);ids=sorted(set(a.ravel()),key=lambda x:(-(a==x).any(axis=1).mean(),int(x)))[:15];sets=[('actual',a,np.ones(len(a)))]
for label,fn in [('earlier',files[2]),('later',files[3])]:
 f=pd.read_csv(root/fn);sets.append((label,f[slots].to_numpy(),f.Copies.to_numpy()))
res={};summ=[]
for label,v,w in sets:
 B=np.array([(v==i).any(axis=1) for i in ids]).T.astype(float);m=w@B/w.sum();joint=B.T@(w[:,None]*B)/w.sum();res[label]=(m,joint,joint-np.outer(m,m))
 left=np.array([50000-sum(salary[i] for i in r) for r in v]);order=np.argsort(left);cdf=np.cumsum(w[order])/sum(w)
 for q in [0,.25,.5,.75,.9,.95,.99,1]:summ.append({'field':label,'quantile':q,'salary_left':int(left[order[min(np.searchsorted(cdf,q,side='left'),len(order)-1)]])})
records=[]
for i,j in itertools.combinations(range(15),2):
 row={'player_a':rev[ids[i]],'player_b':rev[ids[j]]}
 for label,(m,joint,r) in res.items():
  for k,val in [('own_a_pct',m[i]*100),('own_b_pct',m[j]*100),('pair_pct',joint[i,j]*100),('residual_pp',r[i,j]*100)]:row[label+'_'+k]=val
 records.append(row)
pd.DataFrame(records).to_csv(out/'dk-top15-pairs.csv',index=False);pd.DataFrame(summ).to_csv(out/'dk-salary-quantiles.csv',index=False)
(out/'source-manifest.json').write_text(json.dumps({'analysis_date':'2026-10-22','type':'retrospective descriptive audit','code_reference':'0531ddbe6a5340ab1bdc40fc1d5ac8cb9df3e4e2','sources':[{'filename':f,'sha256':hashlib.sha256((root/f).read_bytes()).hexdigest()} for f in files]},indent=2))
assert len(records)==105 and len(summ)==24
print(pd.DataFrame(summ).pivot(index='quantile',columns='field',values='salary_left').to_string())
