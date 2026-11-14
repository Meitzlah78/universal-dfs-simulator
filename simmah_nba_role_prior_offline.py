"""Independent pregame role-prior research; no provider or current-game outcomes."""
import numpy as np
import pandas as pd


def utc(value):
    t=pd.Timestamp(value)
    if t.tzinfo is None or pd.isna(t):
        raise ValueError('Timezone-aware timestamp required')
    return t


def preceding(rows, key, day, cutoff):
    return sorted([r for r in rows if tuple(r['key'])==tuple(key) and r['date']<day
                   and utc(r['completed_at'])<utc(cutoff)], key=lambda r:(r['date'],r['completed_at'],r['game_id']))


def role_from_history(rows, *, minimum_player_history=3, window=5):
    own=rows[-window:]
    if len(own)<minimum_player_history:
        return None
    rate=float(np.mean([r['started'] for r in own]))
    return {'role':'historical_starter' if rate>=.5 else 'historical_reserve',
            'trailing_starter_rate':rate,'history_n':len(own),
            'last_history_date':own[-1]['date']}


def training_examples(rows):
    """Earlier outcomes are labels; role features always precede each label game."""
    result=[]
    for row in rows:
        old=preceding(rows,row['key'],row['date'],row['game_started_at'])
        role=role_from_history(old)
        if role is None:
            continue
        result.append(dict(row,**role,role_verified_pregame=True,
            role_source='earlier verified regular-season boxscore starter flags',
            role_published_at=max(r['completed_at'] for r in old)))
    return result


def current_prior(rows, examples, key, day, capture, *, minimum_training_examples=20):
    capture=utc(capture)
    own=preceding(rows,key,day,capture)
    role=role_from_history(own)
    if role is None:
        return {'supported':False,'reason':'insufficient earlier regular-season role history',
                'history_n':len(own)}
    training=[r for r in examples if r['date']<day and utc(r['completed_at'])<capture and r['role']==role['role']]
    if len(training)<minimum_training_examples:
        return dict(role,supported=False,reason='insufficient earlier same-role training outcomes',training_n=len(training))
    values=np.array([r['minutes'] for r in training],dtype=float)
    return dict(role,supported=True,minutes=float(values.mean()),training_n=len(training),
        latest_training_completion=max(r['completed_at'] for r in training),
        as_of=capture.isoformat(),source='chronological league conditional mean by trailing starter role',
        warning='Historical role only; no verified current lineup/injury promotion or eligibility implied')
