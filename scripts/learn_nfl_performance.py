"""Train NFL candidates from archived games; promote only after later replays."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_nfl_learning import (ROOT,load_archives,fit_candidate,validate_and_promote,atomic_json,fit_joint_replay_candidate)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives',default='data/pbp')
    parser.add_argument('--output-root',default=str(ROOT))
    parser.add_argument('--fit-replays',help='Earlier complete frozen cases used only for volume/dependence fitting')
    parser.add_argument('--replays',help='Directory of full frozen pregame game cases with explicit final raw actuals')
    parser.add_argument('--draws',type=int,default=1024)
    args=parser.parse_args()
    frame,sources=load_archives(Path(args.archives).glob('*.csv.gz'))
    candidate=fit_candidate(frame,sources)
    root=Path(args.output_root)
    if args.fit_replays:
        fitting=[json.loads(p.read_text()) for p in sorted(Path(args.fit_replays).glob('*.json'))]
        candidate=fit_joint_replay_candidate(candidate,fitting,draws=args.draws)
    atomic_json(root/'trials'/(candidate['version']+'.json'),candidate)
    report=candidate
    if args.replays:
        cases=[json.loads(p.read_text()) for p in sorted(Path(args.replays).glob('*.json'))]
        # Validate an immutable earlier candidate, not a new fit containing
        # outcomes from the same validation weeks.
        available=[json.loads(path.read_text()) for path in (root/'trials').glob('*.json')]
        eligible=[trial for trial in available if trial.get('status')=='awaiting full-engine replay'
                  and trial['validation_through']<min(str(case['kickoff'])[:10] for case in cases)]
        if not eligible:raise ValueError('No earlier candidate eligible for these promotion games')
        selected=max(eligible,key=lambda trial:trial['validation_through'])
        report=validate_and_promote(selected,cases,root,draws=args.draws)
    atomic_json(root/'latest_status.json',{'status':report['status'],'version':report['version'],
        'training_games':candidate['training_games'],'validation_games':candidate['validation_games'],
        'active_update':report['status']=='accepted',
        'components':{name:metric['status'] for name,metric in candidate['event_diagnostics'].items()},
        'next_requirement':None if report['status']=='accepted' else 'Later complete frozen game replays; event diagnostics alone never activate a model.'})
    print(json.dumps({'status':report['status'],'version':report['version'],
                     'training_games':candidate['training_games'],'validation_games':candidate['validation_games']},indent=2))

if __name__=='__main__':main()
