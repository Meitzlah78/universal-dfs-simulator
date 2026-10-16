from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text()

import_line = 'from nfl_stat_normalization import historical_two_point_conversions\n'
if import_line not in text:
    anchor = 'from zoneinfo import ZoneInfo\n'
    if anchor not in text:
        raise SystemExit('zoneinfo import anchor not found')
    text = text.replace(anchor, anchor + import_line, 1)

needle = '''            for output_col, source_col in stats_map.items():
                if source_col in rows.columns:
                    stat_line[output_col] = pd.to_numeric(pd.Series([game[source_col]]), errors="coerce").fillna(0).iloc[0]
            scores.append(float(score_nfl_stat_line(stat_line, platform)))
'''
replacement = '''            for output_col, source_col in stats_map.items():
                if source_col in rows.columns:
                    stat_line[output_col] = pd.to_numeric(pd.Series([game[source_col]]), errors="coerce").fillna(0).iloc[0]
            # Normalize all offensive 2PT roles into the shared scoring field.
            stat_line["two_point_conversions"] = historical_two_point_conversions(game)
            scores.append(float(score_nfl_stat_line(stat_line, platform)))
'''
if replacement not in text:
    if needle not in text:
        raise SystemExit('historical scoring anchor not found')
    text = text.replace(needle, replacement, 1)

path.write_text(text)
