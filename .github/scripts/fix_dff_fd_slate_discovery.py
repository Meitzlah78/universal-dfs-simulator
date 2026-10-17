from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text()
old = '''            for slate_date in recent_dates:
                page_url = f"https://www.dailyfantasyfuel.com/nfl/showdown-single-game-projections/fanduel/{slate_date}/"
                page = requests.get(
                    page_url,
                    headers=headers_direct, timeout=30
                )
                page.raise_for_status()
                for table in pd.read_html(io.StringIO(page.text)):
'''
new = '''            from urllib.parse import urljoin
            for slate_date in recent_dates:
                base_url = f"https://www.dailyfantasyfuel.com/nfl/showdown-single-game-projections/fanduel/{slate_date}/"
                page_urls = [base_url]

                # DFF's dated single-game page opens one default matchup. The
                # page also exposes slate-specific links; follow every FanDuel
                # single-game link and let target-player overlap choose the game.
                try:
                    landing = requests.get(base_url, headers=headers_direct, timeout=30)
                    landing.raise_for_status()
                    for href in re.findall(r'href=[\"\\\']([^\"\\\']+)[\"\\\']', landing.text, flags=re.IGNORECASE):
                        href_text = unescape(href).strip()
                        low = href_text.casefold()
                        if 'showdown-single-game-projections/fanduel' not in low:
                            continue
                        candidate = urljoin(base_url, href_text)
                        if candidate not in page_urls:
                            page_urls.append(candidate)
                except Exception:
                    pass

                # The classic FanDuel projection page can expose additional
                # slate codes even when the single-game landing page omits them.
                try:
                    classic_url = f"https://www.dailyfantasyfuel.com/nfl/projections/fanduel/{slate_date}/"
                    classic = requests.get(classic_url, headers=headers_direct, timeout=30)
                    classic.raise_for_status()
                    for code in re.findall(r'[?&]slate=([A-Za-z0-9]+)', classic.text, flags=re.IGNORECASE):
                        candidate = f"https://www.dailyfantasyfuel.com/nfl/showdown-single-game-projections/fanduel/{slate_date}?slate={code}"
                        if candidate not in page_urls:
                            page_urls.append(candidate)
                except Exception:
                    pass

                for page_url in page_urls:
                    try:
                        page = requests.get(page_url, headers=headers_direct, timeout=30)
                        page.raise_for_status()
                        page_tables = pd.read_html(io.StringIO(page.text))
                    except Exception:
                        continue
                    for table in page_tables:
'''
if old not in text:
    raise SystemExit('expected DFF direct-date block not found')
text = text.replace(old, new, 1)
# Improve diagnostics so we can see which slate URL won or was attempted.
text = text.replace(
    'dff_debug.append(f"{slate_date}: rows={len(values)}, overlap={len(overlap)}, name_col={name_col!r}, proj_col={proj_col!r}, sample={_sample_keys!r}")',
    'dff_debug.append(f"{slate_date}: url={page_url}, rows={len(values)}, overlap={len(overlap)}, name_col={name_col!r}, proj_col={proj_col!r}, sample={_sample_keys!r}")',
    1,
)
path.write_text(text)
print('updated DFF FanDuel slate discovery')
