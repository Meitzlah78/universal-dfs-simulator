from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text()
start_marker = '            for slate_date in recent_dates:\n'
end_marker = '            if best_overlap >= min(2, len(target_keys)):\n'
start = text.find(start_marker, text.find('# FanDuel Single Game:'))
end = text.find(end_marker, start)
if start < 0 or end < 0:
    raise SystemExit('current DFF direct-date block not found')
old = text[start:end]
new = '''            from urllib.parse import urljoin
            for slate_date in recent_dates:
                base_url = f"https://www.dailyfantasyfuel.com/nfl/showdown-single-game-projections/fanduel/{slate_date}/"
                page_urls = [base_url]

                # The dated page opens one default matchup. Discover every
                # slate-specific FanDuel Single Game link/candidate first.
                discovery_pages = [
                    base_url,
                    "https://www.dailyfantasyfuel.com/nfl/showdown-single-game-projections/fanduel/",
                    f"https://www.dailyfantasyfuel.com/nfl/projections/fanduel/{slate_date}/",
                ]
                for discovery_url in discovery_pages:
                    try:
                        discovery = requests.get(discovery_url, headers=headers_direct, timeout=30)
                        discovery.raise_for_status()
                    except Exception:
                        continue
                    for href in re.findall(r'href=["\\\']([^"\\\']+)["\\\']', discovery.text, flags=re.IGNORECASE):
                        href_text = unescape(href).strip()
                        low = href_text.casefold()
                        if 'showdown-single-game-projections/fanduel' in low:
                            candidate = urljoin(discovery_url, href_text)
                            if candidate not in page_urls:
                                page_urls.append(candidate)
                    for code in re.findall(r'[?&]slate=([A-Za-z0-9]+)', discovery.text, flags=re.IGNORECASE):
                        candidate = f"https://www.dailyfantasyfuel.com/nfl/showdown-single-game-projections/fanduel/{slate_date}?slate={code}"
                        if candidate not in page_urls:
                            page_urls.append(candidate)

                for page_url in page_urls:
                    try:
                        page = requests.get(page_url, headers=headers_direct, timeout=30)
                        page.raise_for_status()
                        page_tables = pd.read_html(io.StringIO(page.text))
                    except Exception:
                        continue
                    for table in page_tables:
                        if not isinstance(table.columns, pd.MultiIndex):
                            continue
                        if table.shape[1] <= 7:
                            continue
                        name_col = table.columns[2]
                        proj_col = table.columns[7]
                        values = {}
                        for name, projection in zip(table.iloc[:, 2], table.iloc[:, 7]):
                            key = normalize_projection_player_name(name)
                            val = pd.to_numeric(projection, errors="coerce")
                            if key and pd.notna(val) and np.isfinite(float(val)) and float(val) >= 0:
                                values[key] = float(val)
                        overlap = target_keys.intersection(values)
                        _sample_keys = list(values.keys())[:5]
                        dff_debug.append(f"{slate_date}: url={page_url}, rows={len(values)}, overlap={len(overlap)}, name_col={name_col!r}, proj_col={proj_col!r}, sample={_sample_keys!r}")
                        if len(overlap) > best_overlap:
                            best_values = values
                            best_overlap = len(overlap)
                            best_date = slate_date
'''
text = text[:start] + new + text[end:]
path.write_text(text)
print('updated DFF FanDuel slate discovery')
