"""Reconcile an offline rotation audit with saved final NBA CDN box scores."""
import argparse,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_nba_rotation_validation import reconcile_boxscore

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audit',type=Path)
    parser.add_argument('boxscores',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    audit=json.loads(args.audit.read_text());groups={}
    for stint in audit['stints']:groups.setdefault(stint['game_id'],[]).append(stint)
    results=[]
    for gid,stints in sorted(groups.items()):
        path=args.boxscores/('boxscore_'+gid.zfill(10)+'.json')
        if not path.exists():
            results.append({'game_id':gid,'passed':False,'status':'pending: final box score unavailable'})
            continue
        try:
            result=reconcile_boxscore(stints,json.loads(path.read_text()))
            result['boxscore_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        except (ValueError,KeyError,TypeError) as exc:
            result={'game_id':gid,'passed':False,'status':'quarantine: '+str(exc)}
        results.append(result)
    output={'before':audit['before'],'audit_sha256':hashlib.sha256(args.audit.read_bytes()).hexdigest(),
        'live_enabled':False,'games':results,'validated_games':sum(r['passed'] for r in results),
        'pending_games':sum(r['status'].startswith('pending:') for r in results)}
    args.output.write_text(json.dumps(output,indent=2)+'\n')
    print(f"{output['validated_games']}/{len(results)} games reconciled; {output['pending_games']} pending")
if __name__=='__main__':main()
