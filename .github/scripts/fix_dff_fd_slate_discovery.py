from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text()
needle = '''            if best_overlap >= min(2, len(target_keys)):
                return best_values
            st.warning("DFF FanDuel diagnostic — " + ("; ".join(dff_debug) if dff_debug else f"dates={recent_dates!r}; no projection table parsed"))
'''
replacement = '''            if best_overlap >= min(2, len(target_keys)):
                return best_values

            # DFF does not always expose alternate Single Game slate codes in
            # server-rendered HTML. Fall back to the dated FanDuel classic
            # projection table and keep ONLY uploaded-slate players. This gives
            # Single Game the same DFF player projections without guessing a
            # matchup or hardcoding a slate ID.
            classic_best = {}
            classic_overlap = 0
            classic_date = None
            for slate_date in recent_dates:
                classic_url = f"https://www.dailyfantasyfuel.com/nfl/projections/fanduel/{slate_date}/"
                try:
                    classic_page = requests.get(classic_url, headers=headers_direct, timeout=30)
                    classic_page.raise_for_status()
                    classic_tables = pd.read_html(io.StringIO(classic_page.text))
                except Exception:
                    continue
                for table in classic_tables:
                    if not isinstance(table.columns, pd.MultiIndex) or table.shape[1] <= 7:
                        continue
                    values = {}
                    for name, projection in zip(table.iloc[:, 2], table.iloc[:, 7]):
                        key = normalize_projection_player_name(name)
                        val = pd.to_numeric(projection, errors="coerce")
                        if key in target_keys and pd.notna(val) and np.isfinite(float(val)) and float(val) >= 0:
                            values[key] = float(val)
                    if len(values) > classic_overlap:
                        classic_best = values
                        classic_overlap = len(values)
                        classic_date = slate_date
            if classic_overlap >= min(2, len(target_keys)):
                return classic_best

            st.warning("DFF FanDuel diagnostic — " + ("; ".join(dff_debug) if dff_debug else f"dates={recent_dates!r}; no projection table parsed") + f"; classic_fallback={classic_overlap} matches on {classic_date}")
'''
if needle not in text:
    raise SystemExit('DFF return/diagnostic block not found')
text = text.replace(needle, replacement, 1)
path.write_text(text)
print('added DFF FanDuel classic projection fallback')
