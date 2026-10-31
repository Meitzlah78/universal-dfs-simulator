"""Fit/evaluate an offline baseline from minute-verified rotation records."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_nba_rotation_learning import fit_rotation_baseline,evaluate_rotation_baseline

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('records',type=Path);p.add_argument('--before',required=True)
    p.add_argument('--model',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    args=p.parse_args();data=json.loads(args.records.read_text())
    model=fit_rotation_baseline(data,args.before);report=evaluate_rotation_baseline(model,data)
    report['before']=args.before
    args.model.write_text(json.dumps(model,indent=2)+'\n')
    args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(f"Training games: {report['training_games']}; heldout games: {report['heldout_games']}; covered events: {report['covered_replacement_events']}/{report['replacement_events']}")
if __name__=='__main__':main()
