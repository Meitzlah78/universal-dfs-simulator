"""Shared player-pool summaries from completed results, joined by player name."""
import numpy as np
import pandas as pd


def _frame(value):
    return isinstance(value, pd.DataFrame) and not value.empty


def _slots(frame):
    choices = ['QB','RB1','RB2','WR1','WR2','WR3','TE','FLEX','D','DST','Captain','MVP','Flex1','Flex2','Flex3','Flex4','Flex5','FLEX1','FLEX2','FLEX3','FLEX4','FLEX5']
    return [c for c in choices if c in frame.columns]


def complete_player_display(players, outcomes=None, portfolio=None, field=None, ownership=None):
    result = players.copy()
    names = result.Name.astype(str).str.strip()
    if _frame(outcomes):
        summary = outcomes.apply(pd.to_numeric, errors='coerce')
        lookup = {str(c).strip(): c for c in summary.columns}
        for label, q in [('Sim Pts', None), ('Sim P10',.10), ('Sim P25',.25), ('Sim P50',.50), ('Sim P75',.75), ('Sim P90',.90), ('Sim P95',.95), ('Sim P99',.99)]:
            values = summary.mean() if q is None else summary.quantile(q)
            result[label] = names.map({name: values[col] for name,col in lookup.items()}).round(1)
    for label in ['Sim Pts','Sim P10','Sim P25','Sim P50','Sim P75','Sim P90','Sim P95','Sim P99','Cap Hit %']:
        if label not in result:
            result[label] = np.nan
    for frame, label in [(portfolio,'Mine Own %'), (field,'Field Own %')]:
        if _frame(frame) and _slots(frame):
            counts = frame[_slots(frame)].astype(str).apply(lambda row: list(set(row.str.strip())), axis=1).explode().value_counts()
            result[label] = names.map(counts).fillna(0).mul(100/len(frame)).round(1)
            for special, prefix in [('Captain','Captain'),('MVP','MVP')]:
                if special in frame:
                    special_counts = frame[special].astype(str).str.strip().value_counts()
                    special_label = ('Field CPT Own %' if special=='Captain' else 'Field MVP Own %') if label=='Field Own %' else prefix+' Exp %'
                    result[special_label] = names.map(special_counts).fillna(0).mul(100/len(frame)).round(1)
                    flex_label = 'Field FLEX Own %' if label=='Field Own %' else 'Flex Exp %'
                    result[flex_label] = (result[label] - result[special_label]).clip(lower=0).round(1)
        elif label not in result:
            result[label] = np.nan
    result['Exposure %'] = result['Mine Own %']
    source = ownership if _frame(ownership) else result
    own_col = next((c for c in ['Projected Ownership','Ownership %','Ownership','Own%'] if c in source), None)
    if own_col:
        rows = source.drop_duplicates('Name').copy()
        vals = pd.to_numeric(rows[own_col].astype(str).str.replace('%','',regex=False), errors='coerce')
        result['Projected Own %'] = names.map(dict(zip(rows.Name.astype(str).str.strip(),vals)))
        if 'Ownership Source' in rows:
            result['Ownership Source'] = names.map(dict(zip(rows.Name.astype(str).str.strip(),rows['Ownership Source'])))
        elif 'Ownership Source' not in result:
            result['Ownership Source'] = 'Uploaded ownership'
    else:
        result['Projected Own %'] = np.nan
        result['Ownership Source'] = 'Projection-rank popularity fallback (no external ownership)'
    result['Simulation Status'] = np.where(result['Sim Pts'].notna(),'Complete','Pending / player not simulated')
    return result


def scoring_input_report(players,outcomes=None):
    """Export only measured simulation summaries, never projection placeholders."""
    clean=players.drop(columns=[c for c in players if c.startswith('Sim P') or c in {'Sim Pts','Cap Hit %','Simulation Status','Actual Simulation Mean','Simulation Minus Projection'}],errors='ignore').copy()
    report=complete_player_display(clean,outcomes)
    report['Actual Simulation Mean']=np.nan
    if _frame(outcomes):
        report['Actual Simulation Mean']=report.Name.astype(str).str.strip().map(
            {str(c).strip():v for c,v in outcomes.mean().items()})
    report['Simulation Minus Projection']=report['Actual Simulation Mean']-pd.to_numeric(report['Projection'],errors='coerce')
    return report
