from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text(encoding='utf-8')
anchor = '''        # Showdown pages need the slate date in the URL. The Colab notebook
        # confirmed this route works; discover upcoming slate dates from DFF.
        if is_single_game:
'''
if anchor not in text:
    raise SystemExit('DFF showdown fallback anchor not found')

insert = r'''        # DFF's generic single-game page opens one default matchup.  Before
        # falling back to date guessing, follow every slate-specific Showdown
        # link exposed by that page and keep the first table that intersects the
        # salary-file player names.  This makes the selected DK/FD game drive
        # the DFF match instead of whichever game DFF happens to show by default.
        if is_single_game and target_keys:
            try:
                from urllib.parse import urljoin
                slate_links = []
                for href in re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE):
                    href_text = unescape(href).strip()
                    if 'showdown-single-game-projections' not in href_text.casefold():
                        continue
                    if site == 'fanduel' and '/fanduel' not in href_text.casefold():
                        continue
                    if site == 'draftkings' and '/fanduel' in href_text.casefold():
                        continue
                    candidate = urljoin(url, href_text)
                    if candidate != url and candidate not in slate_links:
                        slate_links.append(candidate)

                for slate_url in slate_links:
                    try:
                        slate_page = requests.get(slate_url, headers=headers, timeout=30)
                        slate_page.raise_for_status()
                        slate_tables = pd.read_html(io.StringIO(slate_page.text))
                    except Exception:
                        continue

                    for slate_table in slate_tables:
                        candidate_table = slate_table.copy()
                        if isinstance(candidate_table.columns, pd.MultiIndex):
                            candidate_table = candidate_table.iloc[3:].copy()
                            candidate_table.columns = [
                                str(col[-1]).strip() if isinstance(col, tuple) else str(col).strip()
                                for col in candidate_table.columns
                            ]
                        else:
                            candidate_table.columns = [str(col).strip() for col in candidate_table.columns]

                        normalized_columns = {
                            re.sub(r'[^a-z0-9]+', ' ', str(col).casefold()).strip(): col
                            for col in candidate_table.columns
                        }
                        name_col = next(
                            (col for key, col in normalized_columns.items()
                             if key in ('name', 'player', 'player name', 'nickname') or key.endswith(' name')),
                            None
                        )
                        site_prefix = 'fd' if site == 'fanduel' else 'dk'
                        proj_col = next(
                            (col for key, col in normalized_columns.items()
                             if ('project' in key or 'proj' in key)
                             and (site_prefix in key or 'fantasy points' in key)),
                            None
                        )
                        if proj_col is None:
                            proj_col = next(
                                (col for key, col in normalized_columns.items()
                                 if key in ('dk fp projected', 'fd fp projected', 'ppg projection', 'projection')),
                                None
                            )
                        if name_col is None or proj_col is None:
                            continue

                        slate_result = {}
                        for _, slate_row in candidate_table.iterrows():
                            player_key = normalize_projection_player_name(slate_row.get(name_col, ''))
                            player_value = pd.to_numeric(
                                str(slate_row.get(proj_col, '')).replace(',', '').replace('$', ''),
                                errors='coerce'
                            )
                            if (player_key and pd.notna(player_value)
                                    and np.isfinite(float(player_value)) and float(player_value) >= 0):
                                slate_result[player_key] = float(player_value)

                        # Require a meaningful overlap so one shared/ambiguous
                        # player name cannot select the wrong matchup.
                        overlap = target_keys.intersection(slate_result)
                        required_overlap = min(2, len(target_keys))
                        if slate_result and len(overlap) >= required_overlap:
                            return slate_result
            except Exception:
                pass

'''
text = text.replace(anchor, insert + anchor, 1)
path.write_text(text, encoding='utf-8')
print('Patched DFF single-game slate discovery')
# workflow trigger
