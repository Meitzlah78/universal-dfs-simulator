"""Display-only injury labels: canonical names and upload IDs stay untouched."""
import pandas as pd


def injury_label(name, statuses):
    status = str(statuses.get(str(name), '')).strip().casefold()
    marker = {'questionable': 'Q', 'q': 'Q', 'doubtful': 'D', 'd': 'D', 'out': 'OUT', 'o': 'OUT'}.get(status)
    return f'{name} [{marker}]' if marker else name


def injury_frame(st, frame):
    if not isinstance(frame, pd.DataFrame):
        return frame
    statuses = st.session_state.get('display_injury_statuses', {})
    result = frame.copy()
    if {'Name', 'Injury Status'}.issubset(result):
        statuses = {**statuses, **dict(zip(result['Name'].astype(str), result['Injury Status']))}
    roster_columns = {'Name', 'Player', 'Captain', 'MVP', 'QB', 'TE', 'FLEX', 'DST', 'D', 'RB1', 'RB2', 'WR1', 'WR2', 'WR3'}
    for col in result:
        if col in roster_columns or str(col).lower() in {'flex1', 'flex2', 'flex3', 'flex4', 'flex5'}:
            result[col] = result[col].map(lambda name: injury_label(name, statuses))
    return result


def injury_player_pool(frame):
    """Add a read-only display name while preserving the canonical Name column."""
    result = frame.copy()
    statuses = dict(zip(result['Name'].astype(str), result.get('Injury Status', pd.Series('Active', index=result.index))))
    result['Player'] = result['Name'].map(lambda name: injury_label(name, statuses))
    return result
