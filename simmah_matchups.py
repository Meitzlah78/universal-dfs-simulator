"""Conservative, dated defensive efficiency context; never a point projection."""
import numpy as np
import pandas as pd
from simmah_weather import team_key


def dated_history(history, schedule, kickoff):
    """Exclude undated, same-day and future games (date-only schedules)."""
    cutoff = pd.to_datetime(kickoff, utc=True, errors='coerce')
    if pd.isna(cutoff) or history.empty or schedule.empty or 'game_id' not in history:
        return pd.DataFrame()
    dates = schedule[['game_id', 'gameday']].drop_duplicates('game_id').copy()
    dates['_date'] = pd.to_datetime(dates.gameday, utc=True, errors='coerce')
    rows = history.drop(columns=['_date'], errors='ignore').merge(dates[['game_id','_date']], on='game_id', how='inner')
    # Date-only records cannot establish same-day completion. Stay conservative.
    return rows[(rows._date < cutoff.normalize()) & (rows._date >= cutoff - pd.Timedelta(days=400))].copy()


def matchup_inputs(pool, history, schedule, min_games=4):
    """Return player role additions and an auditable report.

    Position-specific yards per reception/carry are shrunk toward the league
    mean with eight games of prior weight, capped at +/-10%. These are raw
    descriptive rates, not opponent-adjusted skill ratings.
    """
    additions, report = {}, []
    dated = {}
    for row in pool.to_dict('records'):
        pos = str(row.get('Position','')).upper().split('/')[0]
        if pos not in {'QB','RB','WR','TE'}:
            continue
        entry = {'Name':str(row['Name']), 'Opponent':team_key(row.get('Opponent')),
                 'Position':pos, 'Games':0, 'Through':'', 'Status':'Neutral: unverified kickoff/history',
                 'Receiving factor':1., 'Rushing factor':1., 'Sack rate':.065}
        kickoff = str(row.get('Weather Kickoff', ''))
        if kickoff not in dated:
            dated[kickoff] = dated_history(history, schedule, kickoff)
        data = dated[kickoff]
        values = {}
        if not data.empty and {'position','opponent_team'}.issubset(data.columns):
            data = data[data.position.eq(pos)].copy()
            opp = data[data.opponent_team.map(team_key).eq(entry['Opponent'])]
            games = opp.game_id.nunique()
            entry.update(Games=int(games), Through=str(opp._date.max().date()) if games else '')
            entry['Status'] = 'Neutral: insufficient sample'
            if games >= min_games:
                entry['Status'] = 'Historical efficiency context'
                for numerator, denominator, key, label in [
                    ('receiving_yards','receptions','matchup_receiving','Receiving factor'),
                    ('rushing_yards','carries','matchup_rushing','Rushing factor')]:
                    if not {numerator,denominator}.issubset(data.columns):
                        continue
                    league_n = pd.to_numeric(data[numerator], errors='coerce').sum()
                    league_d = pd.to_numeric(data[denominator], errors='coerce').sum()
                    allowed_n = pd.to_numeric(opp[numerator], errors='coerce').sum()
                    allowed_d = pd.to_numeric(opp[denominator], errors='coerce').sum()
                    if league_n > 0 and league_d > 0 and allowed_d >= 20:
                        ratio = (allowed_n/allowed_d)/(league_n/league_d)
                        factor = float(np.clip(1+(ratio-1)*games/(games+8), .9, 1.1))
                        values[key] = entry[label] = factor
                if pos == 'QB' and {'sacks_suffered','attempts'}.issubset(data.columns):
                    sacks = pd.to_numeric(opp.sacks_suffered, errors='coerce').sum()
                    attempts = pd.to_numeric(opp.attempts, errors='coerce').sum()
                    if attempts+sacks >= 100:
                        rate = (sacks + .065*200)/(attempts+sacks+200)
                        values['matchup_sack_rate'] = entry['Sack rate'] = float(np.clip(rate,.04,.09))
                if not values:
                    entry['Status'] = 'Neutral: insufficient opportunities'
        additions[str(row['Name'])] = values
        report.append(entry)
    return additions, pd.DataFrame(report)
