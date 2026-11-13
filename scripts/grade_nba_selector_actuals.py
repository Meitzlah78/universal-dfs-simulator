"""Retrospective actual-score audit; never passes actuals to selector."""
import io,json,zipfile,sys,re
from pathlib import Path
from collections import defaultdict
import pandas as pd
from simmah_nba_learning import name_key
from simmah_nba_scoring import score_nba
from simmah_nba_rules import rules_for

def alias(x):return re.sub(r'(junior|senior|jr|sr|iii|ii|iv)$','',name_key(x))
def run(root):
 root=Path(root);actual=json.loads(zipfile.ZipFile(root/'nba-clock-evidence/Simmah_NBA_Comprehensive_Audit_2026-11-13.zip').read('actual-player-games.json'))
 replays={r['file']:r for p in (root/'nba-selector-results').glob('actual-replay-*.json') for r in json.loads(p.read_text())};results=[]
 for path in sorted((root/'nba-selector-evidence').glob('*Calibration_Solver*.zip')):
  row=replays[path.name];cid=re.search(r'_(\d+(?:-\d+)?)_',path.name)[1];site=row['site'];day=row['date']
  with zipfile.ZipFile(path) as outer:raw=outer.read('original_build.zip') if 'original_build.zip' in outer.namelist() else path.read_bytes()
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   m=json.loads(z.read('inputs/player_pool.json'));pool=pd.DataFrame(m['rows']);pool.attrs=m['attrs'];slots=list(rules_for(pool)['slots'])
   cand=pd.read_csv(io.BytesIO(z.read('candidate_lineups.csv')),dtype=str);saved=pd.read_csv(io.BytesIO(z.read('portfolio_at_build.csv')),dtype=str)
  standings=next((p for p in (root/'nba-selector-standings').iterdir() if cid in p.name),None);official=defaultdict(set);official_ids=defaultdict(set);winner=None
  if standings:
   if standings.suffix=='.zip':
    z=zipfile.ZipFile(standings);raw=z.read(next(n for n in z.namelist() if n.endswith('.csv')))
   else:raw=standings.read_bytes()
   frame=pd.read_csv(io.BytesIO(raw),low_memory=False);winner=float(pd.to_numeric(frame['Points'],errors='coerce').max())
   for _,r in frame[['Player','FPTS']].dropna().iterrows():
    name=str(r['Player']);value=round(float(r['FPTS']),6);match=re.search(r'\((\d+-\d+)\)$',name)
    if match:official_ids[match[1]].add(value);name=name[:match.start()].strip()
    official[name_key(name)].add(value)
  aliases=defaultdict(set)
  for k,values in official.items():aliases[alias(k)].update(values)
  pbp=defaultdict(list)
  for r in actual:
   if r['date']==day:pbp[(r['team'],name_key(r['name']))].append(r)
  scores={};sources={};missing=[]
  for _,p in pool.iterrows():
   pid=str(p['Player ID']);key=name_key(p['Name']);values=official_ids.get(pid) or official.get(key) or aliases.get(alias(key),set())
   if len(values)==1:scores[pid]=next(iter(values));sources[pid]='standings';continue
   matches=pbp.get((p['Team'],key),[])
   if not matches:
    matches=[r for (t,k),items in pbp.items() if t==p['Team'] and alias(k)==alias(key) for r in items]
   if len(matches)==1:
    r=matches[0];scores[pid]=float(score_nba(site,points=r['PTS'],threes=r['PM3'],rebounds=r['REB'],assists=r['AST'],steals=r['STL'],blocks=r['BLK'],turnovers=r['TO']));sources[pid]='boxscore';continue
   missing.append({'id':pid,'name':p['Name'],'team':p['Team']})
  def grade(lineups):
   good=[];missing_ids=set();bad=0
   for lineup in lineups:
    unknown=[p for p in lineup if p not in scores]
    if unknown:bad+=1;missing_ids.update(unknown)
    else:good.append(sum(scores[p] for p in lineup))
   return {'best':max(good) if good else None,'graded':len(good),'ungraded':bad,'complete':not bad,'missing_ids':sorted(missing_ids)}
  result={**row,'contest_id':cid,'field_winner_uploaded_standings':winner,'standings_file':standings.name if standings else None,'pool_actual':grade(cand[slots].values.tolist()),'before_actual':grade(saved[slots].values.tolist()),'after_actual':grade(row['after_lineups']) if 'after_lineups' in row else None,'missing_player_scores':missing,'scoring_sources':dict(pd.Series(list(sources.values())).value_counts().astype(int))}
  result.pop('after_lineups',None);results.append(result)
 (root/'nba-selector-results/actual-comparison.json').write_text(json.dumps(results,indent=2,default=str))
 for r in results:print(r['date'],r['site'],'winner',r['field_winner_uploaded_standings'],'pool',r['pool_actual'],'old',r['before_actual'],'new',r['after_actual'])
if __name__=='__main__':run(*sys.argv[1:])
