from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text(encoding='utf-8')

marker = "        # DFF's generic single-game page opens one default matchup.  Before\n"
date_anchor = '''        # Showdown pages need the slate date in the URL. The Colab notebook
        # confirmed this route works; discover upcoming slate dates from DFF.
        if is_single_game:
'''

# The first workflow was triggered twice and inserted the same link-discovery
# block twice. Keep only the first copy before adding the stronger API fallback.
first = text.find(marker)
if first >= 0:
    second = text.find(marker, first + len(marker))
    if second >= 0:
        end = text.find(date_anchor, second)
        if end >= 0:
            text = text[:second] + text[end:]

if date_anchor not in text:
    raise SystemExit('DFF showdown date fallback anchor not found')

api_marker = '        # DFF slate API can expose multiple games on the same date.'
if api_marker not in text:
    api_block = r'''        # DFF slate API can expose multiple games on the same date.  The old
        # fallback only kept start_date and therefore always opened the first
        # game for that date.  Collect slate/url identifiers too, then test each
        # date+slate combination against the salary-file player names.
        if is_single_game and target_keys:
            try:
                from datetime import date
                from urllib.parse import quote

                slate_response = requests.get(
                    f"https://www.dailyfantasyfuel.com/data/slates/recent/nfl/{site}",
                    headers=headers,
                    timeout=30
                )
                slate_response.raise_for_status()
                slate_payload = slate_response.json()

                candidates = []

                def collect_slate_candidates(node, inherited_date=''):
                    if isinstance(node, dict):
                        node_date = str(
                            node.get('start_date') or node.get('date') or inherited_date or ''
                        ).strip()[:10]
                        slate_code = str(
                            node.get('slate') or node.get('url') or node.get('url_code')
                            or node.get('code') or ''
                        ).strip()
                        if node_date:
                            item = (node_date, slate_code)
                            if item not in candidates:
                                candidates.append(item)
                        for value in node.values():
                            collect_slate_candidates(value, node_date)
                    elif isinstance(node, list):
                        for value in node:
                            collect_slate_candidates(value, inherited_date)

                collect_slate_candidates(slate_payload)
                today = date.today().isoformat()
                candidates.sort(key=lambda item: (item[0] < today, item[0], item[1]))

                def parse_dff_candidate(candidate_html):
                    candidate_result = {}
                    candidate_rows = re.findall(
                        r"<tr\\b[^>]*class=['\\\"][^'\\\"]*projections-listing[^'\\\"]*['\\\"][^>]*>.*?</tr>",
                        candidate_html,
                        flags=re.IGNORECASE | re.DOTALL
                    )
                    for candidate_row in candidate_rows:
                        opening = re.search(r'<tr\\b[^>]*>', candidate_row, flags=re.IGNORECASE | re.DOTALL)
                        opening_tag = opening.group(0) if opening else candidate_row

                        def candidate_attr(attrs, source):
                            for attr in attrs:
                                match = re.search(
                                    r"\\b" + re.escape(attr) + r"\\s*=\\s*['\\\"]([^'\\\"]*)['\\\"]",
                                    source,
                                    flags=re.IGNORECASE
                                )
                                if match:
                                    return unescape(match.group(1)).strip()
                            return ''

                        name = candidate_attr(('data-player', 'data-name'), opening_tag)
                        if not name:
                            name_match = re.search(
                                r"<div\\b[^>]*class=['\\\"][^'\\\"]*\\bbold\\b[^'\\\"]*['\\\"][^>]*>\\s*([^<]+)",
                                candidate_row,
                                flags=re.IGNORECASE | re.DOTALL
                            )
                            if name_match:
                                name = unescape(name_match.group(1)).strip()
                        projection = candidate_attr(
                            ('data-ppg_proj', 'data-ppg-proj', 'data-value_proj', 'data-projection'),
                            candidate_row
                        )
                        value = pd.to_numeric(projection, errors='coerce')

                        if pd.isna(value):
                            cells = re.findall(
                                r'<td\\b[^>]*>(.*?)</td>', candidate_row,
                                flags=re.IGNORECASE | re.DOTALL
                            )
                            if len(cells) > 6:
                                visible = unescape(re.sub(r'<[^>]+>', ' ', cells[6]))
                                visible = re.sub(r'\\s+', ' ', visible).strip()
                                value = pd.to_numeric(
                                    visible.replace(',', '').replace('$', ''), errors='coerce'
                                )

                        key = normalize_projection_player_name(name)
                        if key and pd.notna(value) and np.isfinite(float(value)) and float(value) >= 0:
                            candidate_result[key] = float(value)
                    return candidate_result

                for slate_date, slate_code in candidates:
                    base = (
                        f"https://www.dailyfantasyfuel.com/nfl/"
                        f"showdown-single-game-projections/{site}/{slate_date}"
                    )
                    candidate_urls = []
                    if slate_code:
                        encoded = quote(slate_code, safe='')
                        candidate_urls.extend([
                            f"{base}?slate={encoded}",
                            f"{base}?url={encoded}",
                        ])
                    candidate_urls.append(base + '/')

                    for candidate_url in candidate_urls:
                        try:
                            candidate_response = requests.get(candidate_url, headers=headers, timeout=30)
                            candidate_response.raise_for_status()
                        except Exception:
                            continue
                        candidate_result = parse_dff_candidate(candidate_response.text)
                        overlap = target_keys.intersection(candidate_result)
                        required_overlap = min(2, len(target_keys))
                        if candidate_result and len(overlap) >= required_overlap:
                            return candidate_result
            except Exception:
                pass

'''
    text = text.replace(date_anchor, api_block + date_anchor, 1)

path.write_text(text, encoding='utf-8')
print('Patched DFF single-game slate API discovery')
