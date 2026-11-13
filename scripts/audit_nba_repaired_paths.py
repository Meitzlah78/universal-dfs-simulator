"""Read-only repaired ESPN reconstruction and role-policy provenance checks."""
import json,gzip,zipfile,io,sys
from pathlib import Path
from collections import Counter
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_nba_espn_rotations import reconstruct_rotations
from simmah_nba_role_policy_offline import blend_stale_provider_roles

def run(root,evidence,output):
 rows=[]
 for path in sorted((Path(root)/'data/nba_pbp').glob('*/*.json.gz')):
  game=json.loads(gzip.decompress(path.read_bytes()));result=reconstruct_rotations(game)
  rows.append({'game_id':game['event_id'],'date':game['date'],'complete':result['complete'],
               'minute_ledger':sum(result['player_minutes'].values()),'issues':result['issues']})
 policy=[]
 for path in sorted(Path(evidence).glob('*Calibration_Solver*.zip')):
  with zipfile.ZipFile(path) as z:
   data=z.read('original_build.zip') if 'original_build.zip' in z.namelist() else path.read_bytes()
  with zipfile.ZipFile(io.BytesIO(data)) as z:
   meta=json.loads(z.read('inputs/player_pool.json'));manifest=json.loads(z.read('manifest.json'))
  pool=pd.DataFrame(meta['rows']);pool.attrs=meta['attrs']
  tested=blend_stale_provider_roles(pool,manifest['slate_date'])
  policy.append({'package':path.name,'counts':tested.attrs['offline_role_policy'],
    'recorded_applied_archive_players':pool.attrs.get('nba_learning',{}).get('matched_players'),
    'provider_source_rows':int(pool.get('Role Rate Source',pd.Series(dtype=str)).astype(str).str.startswith('Individual historical rates').sum())})
 report={'live_enabled':False,'espn_games':len(rows),'complete_reconstructions':sum(v['complete'] for v in rows),
  'issue_counts':dict(Counter(i['reason'] for r in rows for i in r['issues'])),'games':rows,'role_policy':policy,
  'limitations':['A repaired import is not a guarantee of full source lineup coverage','Complete requires endpoint and five-player floor evidence; actual-minute reconciliation remains separate','No unknown-age provider role overwritten; stale blend remains offline and unvalidated']}
 Path(output).write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k not in ['games','role_policy']},indent=2))
if __name__=='__main__':run(*sys.argv[1:])
