"""Nightly train -> held-out validation -> approved historical-role activation."""
from datetime import datetime
import gzip,hashlib,json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_nba_learning import train_and_validate,load_approved
from simmah_nba_roles import observations


def run(archive_root,model_root,today):
    model_root=Path(model_root);games=[];rejected=[]
    for path in sorted(Path(archive_root).glob('*/*.json.gz')):
        try:
            with gzip.open(path,'rt') as stream:g=json.load(stream)
            if g['date']>=today:continue
            # Recheck cached source integrity before it enters training.
            last=g['events'][-1]
            if int(last['homeScore'])!=g['home_score'] or int(last['awayScore'])!=g['away_score']:
                raise ValueError('Final score mismatch')
            list(observations([g],today))
            games.append(g)
        except (ValueError,KeyError,TypeError,OSError,EOFError) as exc:
            rejected.append({'file':path.parent.name+'/'+path.name,'reason':str(exc)})
    incumbent=load_approved(today,model_root)
    baseline=json.loads((model_root/'position-roles-before-2026-04-09.json').read_text())
    report=train_and_validate(games,today,baseline,incumbent)
    model=report.pop('model',None)
    report.update(rejected_archive_games=rejected,corpus_games=len(games),as_of=today)
    reports=model_root/'learning_reports';reports.mkdir(parents=True,exist_ok=True)
    (reports/(today+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    if model:
        directory=model_root/'learned_roles';directory.mkdir(exist_ok=True)
        payload=(json.dumps(model,indent=2,sort_keys=True)+'\n').encode()
        filename='learned_roles/'+model['version']+'.json'
        (model_root/filename).write_bytes(payload)
        index_path=model_root/'learned_roles_index.json'
        index=json.loads(index_path.read_text()) if index_path.exists() else {'schema':1,'versions':[]}
        record={'version':model['version'],'activation_date':today,'file':filename,
            'sha256':hashlib.sha256(payload).hexdigest()}
        index['versions']=[r for r in index['versions'] if r['version']!=model['version']]+[record]
        temporary=index_path.with_suffix('.tmp');temporary.write_text(json.dumps(index,indent=2)+'\n');temporary.replace(index_path)
    print(json.dumps(report,indent=2))
    return report

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    run(root/'data/nba_pbp',root/'data/nba_models',datetime.now(ZoneInfo('America/New_York')).date().isoformat())
