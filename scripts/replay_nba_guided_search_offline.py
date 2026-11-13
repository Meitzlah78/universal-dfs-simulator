"""Frozen-input, predeclared guided search comparison. No live modifications."""
import io,json,re,sys,zipfile,time,hashlib
from pathlib import Path
import numpy as np,pandas as pd
from simmah_nba_guided_search_offline import build_candidates
from simmah_nba_candidates import build_candidates as live_build
from simmah_nba_contest import evaluate_candidates,select_entries
from simmah_nba_rules import rules_for
from simmah_nba_rosters import validate_lineup

def run(workspace,cid,search_seed):
 root=Path(workspace);out=root/'nba-guided-search-results';search_seed=int(search_seed);policy=json.loads((out/'policy.json').read_text());path=next((root/'nba-selector-evidence').glob('*'+cid+'*'))
 with zipfile.ZipFile(path) as outer:raw=outer.read('original_build.zip') if 'original_build.zip' in outer.namelist() else path.read_bytes()
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  manifest=json.loads(z.read('manifest.json'))
  for name,info in manifest['files'].items():
   if hashlib.sha256(z.read(name)).hexdigest()!=info['sha256']:raise ValueError('Frozen source mismatch')
  meta=json.loads(z.read('inputs/player_pool.json'));pool=pd.DataFrame(meta['rows']);pool.attrs=meta['attrs'];pool['Player ID']=pool['Player ID'].astype(str);arrays=np.load(io.BytesIO(z.read('solver/arrays.npz')));settings=json.loads(z.read('inputs/settings.json'));rules=rules_for(pool);slots=list(rules['slots']);lookup={pid:i for i,pid in enumerate(pool['Player ID'])}
  field=pd.read_csv(io.BytesIO(z.read('opponent_field.csv')),dtype={s:str for s in slots});field_ix=np.array([[lookup[p] for p in row] for row in field[slots].values]);copies=field.Copies.to_numpy(int)
 construction=arrays['outcomes_seed_83'];evaluation=arrays['outcomes_seed_2100'];frozen_hash=hashlib.sha256(construction.tobytes()+evaluation.tobytes()).hexdigest()
 fullcid=re.search(r'_(\d+-\d+)_',path.name)[1];standings=pd.read_csv(root/'nba-selector-standings'/f'{fullcid}.csv',low_memory=False);winner=standings.loc[pd.to_numeric(standings.Points,errors='coerce').idxmax()];winner_ids=set(re.findall(r'\((\d+-\d+)\)',winner.Lineup));actual={}
 for _,row in standings[['Player','FPTS']].dropna().iterrows():
  m=re.search(r'\((\d+-\d+)\)$',str(row.Player))
  if m:actual[m[1]]=float(row.FPTS)
 def grade(rows):
  good=[sum(actual[p] for p in row) for row in rows if all(p in actual for p in row)];threshold=400. if cid=='136378' else 370.
  return {'best':max(good) if good else None,'graded':len(good),'ungraded':len(rows)-len(good),'threshold':threshold,'at_threshold':sum(v>=threshold for v in good),'at_field_winner':sum(v>=float(winner.Points) for v in good)}
 result=[];checkpoint=out/f'{cid}-{search_seed}.json'
 if checkpoint.exists():result=json.loads(checkpoint.read_text())
 for arm in ['baseline','correlation25','environment']:
  if any(r['arm']==arm for r in result):continue
  started=time.monotonic();kwargs={'target':5000,'seed':search_seed,'salary_min':58000,'salary_aware':settings['salary_aware'],'correlation':25 if arm=='correlation25' else 0}
  guide={'focus_probability':.35,'utility_bonus_scale':.25} if arm=='environment' else None
  proposed=build_candidates(pool,construction,environment_guidance=guide,**kwargs);indices=proposed.pop('indices');generation_seconds=time.monotonic()-started
  if arm=='baseline':np.testing.assert_array_equal(indices,live_build(pool,construction,**kwargs)['indices'])
  ids=pool['Player ID'].to_numpy()[indices]
  for row in ids:validate_lineup(pool,row.tolist(),salary_cap=rules['salary_cap'],max_from_team=rules['max_from_team'],salary_min=58000)
  np.savez_compressed(out/f'{cid}-{search_seed}-{arm}.npz',indices=indices)
  report=evaluate_candidates(evaluation,indices,field_ix,arrays['payouts'],settings['entry_fee'],construction_seed=83,evaluation_seed=2100,field_copies=copies,score_ticks=rules['score_ticks'])
  selected=select_entries(pool,indices,report,20,diversity=100,metric='Top 1%');pairs={tuple(sorted((pool.iloc[lookup[p]].Team,pool.iloc[lookup[p]].Opponent))) for p in winner_ids};stacks={}
  for game in pairs:
   gp=set(pool.loc[pool.apply(lambda p:tuple(sorted((p.Team,p.Opponent)))==game,axis=1),'Player ID']);count=len(gp&winner_ids);stacks[str(game)]={'winner_players':count,'candidates_at_least_that_many':sum(len(set(row)&gp)>=count for row in ids)}
  if hashlib.sha256(construction.tobytes()+evaluation.tobytes()).hexdigest()!=frozen_hash:raise ValueError('Saved outcomes mutated')
  record={'contest_id':fullcid,'date':manifest['slate_date'],'seed':search_seed,'arm':arm,'policy_sha256':hashlib.sha256((out/'policy.json').read_bytes()).hexdigest(),'candidate_metadata':proposed,'generation_seconds':generation_seconds,'total_seconds':time.monotonic()-started,'winner_present':any(set(row)==winner_ids for row in ids),'pool_actual':grade(ids.tolist()),'selected_actual':grade(selected[slots].values.tolist()),'stack_counts':stacks,'selected_metadata':selected.attrs,'legal_candidates':len(ids),'unique_candidates':len({tuple(sorted(row)) for row in ids}),'unchanged_outcome_sha256':frozen_hash}
  selected.to_json(out/f'{cid}-{search_seed}-{arm}-selected.json',orient='records');result.append(record);temp=checkpoint.with_suffix('.tmp');temp.write_text(json.dumps(result,indent=2,default=str));temp.replace(checkpoint);print(cid,search_seed,arm,record['pool_actual'],record['selected_actual'],flush=True)
if __name__=='__main__':run(*sys.argv[1:])
