from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text(encoding='utf-8')

# FanDuel single-game slate URL routing.
old = '''        if is_single_game:
            # This is the working Colab route; DraftKings is the default view.
            url = (
                "https://www.dailyfantasyfuel.com/nfl/showdown-single-game-projections/"
                if site == "draftkings"
                else "https://www.dailyfantasyfuel.com/nfl/showdown-single-game-projections/fanduel/"
            )
'''
new = '''        if is_single_game:
            # FanDuel's generic page can point at a different slate. The
            # slate-discovery fallback below resolves the actual date + slate
            # identifier and matches it against the uploaded salary names.
            url = (
                "https://www.dailyfantasyfuel.com/nfl/showdown-single-game-projections/"
                if site == "draftkings"
                else "https://www.dailyfantasyfuel.com/nfl/projections/fanduel/"
            )
'''
if old in text:
    text = text.replace(old, new, 1)

old_base = '''                for slate_date, slate_code in candidates:
                    base = (
                        f"https://www.dailyfantasyfuel.com/nfl/"
                        f"showdown-single-game-projections/{site}/{slate_date}"
                    )
                    candidate_urls = []
'''
new_base = '''                for slate_date, slate_code in candidates:
                    if site == 'fanduel':
                        base = (
                            f"https://www.dailyfantasyfuel.com/nfl/"
                            f"projections/fanduel/{slate_date}"
                        )
                    else:
                        base = (
                            f"https://www.dailyfantasyfuel.com/nfl/"
                            f"showdown-single-game-projections/{site}/{slate_date}"
                        )
                    candidate_urls = []
'''
if old_base in text:
    text = text.replace(old_base, new_base, 1)

# DFF current MultiIndex headers: preserve real rows and select the last useful
# (non-Unnamed) header level, which yields NAME and FD FP PROJECTED.
old_flatten = '''            if isinstance(dff_table.columns, pd.MultiIndex):
                dff_table = dff_table.iloc[3:].copy()
                dff_table.columns = [
                    str(col[-1]).strip() if isinstance(col, tuple) else str(col).strip()
                    for col in dff_table.columns
                ]
'''
new_flatten = '''            if isinstance(dff_table.columns, pd.MultiIndex):
                def _dff_header(col):
                    parts = [str(part).strip() for part in col]
                    useful = [part for part in parts if part and not part.casefold().startswith("unnamed:")]
                    return useful[-1] if useful else parts[-1]
                dff_table.columns = [_dff_header(col) for col in dff_table.columns]
'''
if old_flatten in text:
    text = text.replace(old_flatten, new_flatten, 1)

old_candidate_flatten = '''                        if isinstance(candidate_table.columns, pd.MultiIndex):
                            candidate_table = candidate_table.iloc[3:].copy()
                            candidate_table.columns = [
                                str(col[-1]).strip() if isinstance(col, tuple) else str(col).strip()
                                for col in candidate_table.columns
                            ]
'''
new_candidate_flatten = '''                        if isinstance(candidate_table.columns, pd.MultiIndex):
                            def _dff_candidate_header(col):
                                parts = [str(part).strip() for part in col]
                                useful = [part for part in parts if part and not part.casefold().startswith("unnamed:")]
                                return useful[-1] if useful else parts[-1]
                            candidate_table.columns = [_dff_candidate_header(col) for col in candidate_table.columns]
'''
text = text.replace(old_candidate_flatten, new_candidate_flatten)

# The date+slate fallback was still feeding each candidate page to the obsolete
# tr.projections-listing parser. DFF's current FanDuel page has zero such rows,
# but pd.read_html returns the complete projection table. Parse that table here.
old_call = '''                        candidate_result = parse_dff_candidate(candidate_response.text)
                        overlap = target_keys.intersection(candidate_result)
'''
new_call = '''                        candidate_result = {}
                        try:
                            candidate_tables = pd.read_html(io.StringIO(candidate_response.text))
                        except Exception:
                            candidate_tables = []
                        for candidate_table in candidate_tables:
                            candidate_table = candidate_table.copy()
                            if isinstance(candidate_table.columns, pd.MultiIndex):
                                def _candidate_header(col):
                                    parts = [str(part).strip() for part in col]
                                    useful = [part for part in parts if part and not part.casefold().startswith("unnamed:")]
                                    return useful[-1] if useful else parts[-1]
                                candidate_table.columns = [_candidate_header(col) for col in candidate_table.columns]
                            else:
                                candidate_table.columns = [str(col).strip() for col in candidate_table.columns]
                            normalized = {
                                re.sub(r"[^a-z0-9]+", " ", str(col).casefold()).strip(): col
                                for col in candidate_table.columns
                            }
                            candidate_name_col = next(
                                (col for key, col in normalized.items()
                                 if key in ("name", "player", "player name", "nickname") or key.endswith(" name")),
                                None
                            )
                            candidate_site_prefix = "fd" if site == "fanduel" else "dk"
                            candidate_proj_col = next(
                                (col for key, col in normalized.items()
                                 if ("project" in key or "proj" in key)
                                 and (candidate_site_prefix in key or "fantasy points" in key)),
                                None
                            )
                            if candidate_name_col is None or candidate_proj_col is None:
                                continue
                            for _, candidate_row in candidate_table.iterrows():
                                player_key = normalize_projection_player_name(candidate_row.get(candidate_name_col, ""))
                                player_value = pd.to_numeric(
                                    str(candidate_row.get(candidate_proj_col, "")).replace(",", "").replace("$", ""),
                                    errors="coerce"
                                )
                                if player_key and pd.notna(player_value) and np.isfinite(float(player_value)) and float(player_value) >= 0:
                                    candidate_result[player_key] = float(player_value)
                            if candidate_result:
                                break
                        overlap = target_keys.intersection(candidate_result)
'''
if old_call in text:
    text = text.replace(old_call, new_call, 1)
elif 'candidate_tables = pd.read_html(io.StringIO(candidate_response.text))' not in text:
    raise SystemExit('DFF candidate parser call not found')

path.write_text(text, encoding='utf-8')
print('Patched DFF FanDuel slate candidate pages to parse current projection tables')
