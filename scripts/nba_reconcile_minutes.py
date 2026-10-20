"""Audit explicitly mapped frozen pregame and final-actual CSVs; no live writes."""
import argparse
import json
from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_nba_reconciliation import reconcile_minutes

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pregame',required=True);p.add_argument('--actuals',required=True)
    p.add_argument('--output-dir',required=True)
    a=p.parse_args()
    pre=pd.read_csv(a.pregame,dtype={'Game ID':str,'NBA Player ID':str})
    actual=pd.read_csv(a.actuals,dtype={'Game ID':str,'NBA Player ID':str})
    result=reconcile_minutes(pre,actual)
    out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True)
    result.pop('rows').to_csv(out/'reconciled-minutes.csv',index=False)
    (out/'audit.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps(result,indent=2,allow_nan=False))
