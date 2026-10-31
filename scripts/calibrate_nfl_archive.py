"""Offline temporal calibration of NFL fallback rates; never changes live inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

BASELINE={'early_down_pass_rate':.58,'sack_rate':.065,'interception_given_no_sack':.021,'completion_given_no_sack_or_interception':.64}
REQUIRED={'season','week','game_id','play_id','game_date','qtr','game_seconds_remaining','play_type','down','sack','interception','complete_pass','yards_gained'}


def load_archive(path,week):
    frame=pd.read_csv(path)
    missing=REQUIRED-set(frame)
    if missing:raise ValueError('Missing archive columns: '+', '.join(sorted(missing)))
    if frame.empty or not frame['week'].eq(week).all() or not frame['season'].eq(2026).all():
        raise ValueError('Archive must contain only the requested 2026 week')
    if frame.duplicated(['game_id','play_id']).any():raise ValueError('Duplicate game/play IDs')
    audit=[]
    for game,rows in frame.groupby('game_id',sort=True):
        regulation=rows[pd.to_numeric(rows.qtr,errors='coerce').le(4)]
        if regulation.empty or not pd.to_numeric(regulation.game_seconds_remaining,errors='coerce').eq(0).any():
            raise ValueError('Regulation-end marker missing: '+str(game))
        audit.append({'game_id':game,'rows':len(rows),'max_quarter':int(rows.qtr.max()),'regulation_end_present':True})
    return frame,{'rows':len(frame),'games':len(audit),'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),'game_audit':audit}


def samples(frame):
    # The live engine is regulation-only; exclude OT and all conversion plays.
    regulation=frame[pd.to_numeric(frame.qtr,errors='coerce').between(1,4)].copy()
    for column in ('two_point_attempt','extra_point_attempt'):
        if column in regulation:
            regulation=regulation[pd.to_numeric(regulation[column],errors='coerce').fillna(0).eq(0)]
    plays=regulation[regulation.play_type.isin(['pass','run'])]
    early=plays[pd.to_numeric(plays.down,errors='coerce').between(1,3)]
    passing=plays[plays.play_type.eq('pass')]
    def flag(rows,column):
        values=pd.to_numeric(rows[column],errors='coerce')
        if values.isna().any() or not values.isin([0,1]).all():raise ValueError('Missing/invalid event flags: '+column)
        return values.to_numpy(float)
    sacks=flag(passing,'sack')
    no_sack=passing.loc[sacks==0]
    interceptions=flag(no_sack,'interception')
    clean=no_sack.loc[interceptions==0]
    events={'early_down_pass_rate':early.play_type.eq('pass').to_numpy(float),
        'sack_rate':sacks,'interception_given_no_sack':interceptions,
        'completion_given_no_sack_or_interception':flag(clean,'complete_pass')}
    if any(not len(values) for values in events.values()):raise ValueError('Empty event denominator')
    yardage={}
    for name,rows in [('yards_per_completion',clean[clean.complete_pass.eq(1)]),('yards_per_rush',plays[plays.play_type.eq('run')])]:
        values=pd.to_numeric(rows.yards_gained,errors='coerce')
        if not len(values) or not np.isfinite(values).all():raise ValueError('Missing yardage: '+name)
        yardage[name]={'count':len(values),'mean':float(values.mean())}
    return events,yardage


def calibrate(train_path,test_path,prior_exposures=1000.):
    if not np.isfinite(prior_exposures) or prior_exposures<=0:raise ValueError('Positive prior exposure required')
    train,train_audit=load_archive(train_path,5);test,test_audit=load_archive(test_path,6)
    if set(train.game_id)&set(test.game_id):raise ValueError('Training/test game overlap')
    if pd.to_datetime(train.game_date,utc=True).max()>=pd.to_datetime(test.game_date,utc=True).min():
        raise ValueError('Training must precede all evaluation games')
    train_events,train_yards=samples(train);test_events,test_yards=samples(test)
    rows=[]
    for name,baseline in BASELINE.items():
        old=train_events[name];actual=test_events[name]
        fitted=float((old.sum()+prior_exposures*baseline)/(len(old)+prior_exposures))
        def loss(p):return float(-(actual*np.log(p)+(1-actual)*np.log1p(-p)).mean())
        rows.append({'metric':name,'baseline_default':baseline,'train_count':len(old),
            'train_observed':float(old.mean()),'fitted':fitted,'test_count':len(actual),
            'test_observed':float(actual.mean()),'baseline_log_loss':loss(baseline),
            'fitted_log_loss':loss(fitted),'log_loss_change':loss(fitted)-loss(baseline)})
    return {'status':'offline exploratory temporal holdout; no live parameters changed',
        'training':train_audit,'evaluation':test_audit,'prior_exposures':prior_exposures,
        'metrics':rows,'yardage_observations':{'week5':train_yards,'week6':test_yards},
        'caveats':['Protocol constructed after Week 6 outcomes; not a prospective trial.',
        'Baseline defaults only: live player histories, margins, weather and market gains are not reproduced.',
        'One training week and one evaluation week cannot establish persistent improvement or lineup ROI.',
        'Regulation-end markers checked in archive; not independent official final-status verification.',
        'Overtime, conversions, kneels and spikes excluded by quarter/play-type filters.',
        'Sacks/pass definitions use recorded pass play_type; QB scrambles are recorded runs.',
        'Archive lacks fumble-loss, kick-result and complete scoring fields; no DK/FD actual fantasy scores reconstructed.',
        'No frozen player predictions, tail probabilities, lineups or opponent fields are evaluated here.']}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--train',required=True);parser.add_argument('--test',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();report=calibrate(args.train,args.test)
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
    for row in report['metrics']:print(row['metric'], 'baseline',round(row['baseline_default'],4),'fitted',round(row['fitted'],4),'week6',round(row['test_observed'],4),'logloss change',round(row['log_loss_change'],6))
