"""Offline pregame input check using cached public provider responses."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simmah_nba_import import read_template
from simmah_nba_projections import parse_rotowire,apply_projections,slate_date
from simmah_nba_role_priors import apply_position_priors
from simmah_nba_markets import extract_markets
from simmah_nba_pregame import PregameEngine
from simmah_nba_engine import EventRates

def prepare_inputs(template,players,projections,models):
    path=Path(template);day=slate_date(path.name)
    pool=read_template(path.read_bytes())['players']
    values,details=parse_rotowire(json.loads(Path(players).read_text()),json.loads(Path(projections).read_text()),day,pool)
    pool=apply_projections(pool,values)
    for i,row in pool.iterrows():
        detail=details.get((row['Name'].casefold(),row['Team']),{})
        for col,value in detail.items():pool.at[i,col]=value
        if str(detail.get('RotoWire Injury','')).upper() in {'O','OUT','IR','SUSPENDED'}:
            pool.at[i,'Injury Status']='Out';pool.at[i,'Eligible']=False
    model=Path(models)
    pool=apply_position_priors(pool,json.loads((model/'position-roles-before-2026-04-09.json').read_text()),day)
    baseline=json.loads((model/'event-rates-before-2026-04-09.json').read_text())
    if baseline['before']>day:raise ValueError('Historical baseline follows target date')
    return pool,extract_markets(pool),EventRates(**baseline['rates'])

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for arg in ('template','players','projections'):p.add_argument('--'+arg,required=True)
    p.add_argument('--models',default=str(Path(__file__).resolve().parents[1]/'data'/'nba_models'))
    p.add_argument('--simulations',type=int,default=1000)
    a=p.parse_args()
    pool,markets,rates=prepare_inputs(a.template,a.players,a.projections,a.models)
    engine=PregameEngine(pool,markets,rates)
    scores=engine(a.simulations,83)
    print(json.dumps({'shape':scores.shape,'game_reports':engine.last_report},indent=2))
