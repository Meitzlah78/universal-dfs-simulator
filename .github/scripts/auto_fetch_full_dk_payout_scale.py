from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

old = '''                # Some responses include structured payout tiers. Only accept tiers when
                # rank and prize values are explicit; never guess a full payout table from prose.
                _payout_rows = []
                _rank_keys = ("rank", "place", "position", "finish", "minRank", "min_rank", "startRank")
                _prize_keys = ("prize", "payout", "winnings", "amount", "prizeAmount", "payoutAmount")
                def _walk_dk_payout_objects(obj):
                    if isinstance(obj, dict):
                        normalized = {str(k).casefold(): v for k, v in obj.items()}
                        rank_value = next((normalized[k.casefold()] for k in _rank_keys if k.casefold() in normalized), None)
                        prize_value = next((normalized[k.casefold()] for k in _prize_keys if k.casefold() in normalized), None)
                        if rank_value is not None and prize_value is not None:
                            try:
                                rank_num = int(float(str(rank_value).replace(",", "")))
                                prize_num = float(str(prize_value).replace("$", "").replace(",", ""))
                                end_value = next((normalized[k.casefold()] for k in ("maxRank", "max_rank", "endRank", "toRank") if k.casefold() in normalized), rank_num)
                                end_num = int(float(str(end_value).replace(",", "")))
                                if rank_num >= 1 and end_num >= rank_num and prize_num >= 0:
                                    for rank in range(rank_num, min(end_num, 100000) + 1):
                                        _payout_rows.append((rank, prize_num))
                            except (TypeError, ValueError):
                                pass
                        for child in obj.values():
                            _walk_dk_payout_objects(child)
                    elif isinstance(obj, list):
                        for child in obj:
                            _walk_dk_payout_objects(child)
                _walk_dk_payout_objects(_dk_payload)
                if _payout_rows:
                    _payout_df = pd.DataFrame(_payout_rows, columns=["Rank", "Prize"]).drop_duplicates("Rank", keep="last")
                    _payout_df = _payout_df.sort_values("Rank")
                    _payout_schedule_auto = np.zeros(int(_payout_df["Rank"].max()), dtype=float)
                    _payout_schedule_auto[_payout_df["Rank"].to_numpy(dtype=int) - 1] = _payout_df["Prize"].to_numpy(dtype=float)
                    st.session_state["contest_payout_schedule"] = _payout_schedule_auto
                    st.session_state["contest_payout_source_name"] = "DraftKings contest details API"
                    st.session_state["contest_payout_contest_id"] = _contest_id_for_api
                    st.session_state["contest_payout_auto_loaded"] = True
                    st.success(f"DraftKings returned a structured payout table with {_payout_df['Rank'].nunique():,} ranks.")
                else:
                    st.session_state["contest_payout_auto_loaded"] = False
                    st.info(
                        "DraftKings returned contest details, but no complete rank-by-rank payout table was exposed. "
                        "Review the summary below and upload the payout table CSV to calculate expected prizes."
                    )
'''

new = '''                # Find a complete payout ladder automatically. DraftKings sometimes puts
                # tiers in structured JSON, sometimes in embedded page text. Never accept
                # a partial ladder: ranks must be contiguous from 1 through the last paid
                # position, and when a prize-pool total is available the dollars must match.
                _payout_rows = []
                _rank_keys = ("rank", "place", "position", "finish", "minRank", "min_rank", "startRank")
                _prize_keys = ("prize", "payout", "winnings", "amount", "prizeAmount", "payoutAmount")

                def _add_payout_range(start_rank, end_rank, prize):
                    try:
                        start_rank = int(start_rank)
                        end_rank = int(end_rank)
                        prize = float(prize)
                    except (TypeError, ValueError):
                        return
                    if start_rank < 1 or end_rank < start_rank or end_rank > 100000 or prize <= 0:
                        return
                    for rank in range(start_rank, end_rank + 1):
                        _payout_rows.append((rank, prize))

                def _walk_dk_payout_objects(obj):
                    if isinstance(obj, dict):
                        normalized = {str(k).casefold(): v for k, v in obj.items()}
                        rank_value = next((normalized[k.casefold()] for k in _rank_keys if k.casefold() in normalized), None)
                        prize_value = next((normalized[k.casefold()] for k in _prize_keys if k.casefold() in normalized), None)
                        if rank_value is not None and prize_value is not None:
                            try:
                                rank_num = int(float(str(rank_value).replace(",", "")))
                                prize_num = float(str(prize_value).replace("$", "").replace(",", ""))
                                end_value = next((normalized[k.casefold()] for k in ("maxRank", "max_rank", "endRank", "toRank") if k.casefold() in normalized), rank_num)
                                end_num = int(float(str(end_value).replace(",", "")))
                                _add_payout_range(rank_num, end_num, prize_num)
                            except (TypeError, ValueError):
                                pass
                        for child in obj.values():
                            _walk_dk_payout_objects(child)
                    elif isinstance(obj, list):
                        for child in obj:
                            _walk_dk_payout_objects(child)

                def _parse_payout_text(value):
                    import html as _html
                    raw = _html.unescape(str(value or ""))
                    if "$" not in raw:
                        return
                    cleaned = re.sub(r"<[^>]+>", " ", raw)
                    cleaned = re.sub(r"\\s+", " ", cleaned)
                    occupied = []
                    range_pattern = re.compile(
                        r"(?<!\\d)(\\d{1,6})(?:st|nd|rd|th)?\\s*(?:-|–|—|to)\\s*"
                        r"(\\d{1,6})(?:st|nd|rd|th)?[^$]{0,40}\\$\\s*"
                        r"([0-9][0-9,]*(?:\\.[0-9]{1,2})?)",
                        flags=re.IGNORECASE,
                    )
                    for match in range_pattern.finditer(cleaned):
                        _add_payout_range(
                            match.group(1), match.group(2), match.group(3).replace(",", "")
                        )
                        occupied.append(match.span())

                    single_pattern = re.compile(
                        r"(?<!\\d)(\\d{1,6})(?:st|nd|rd|th)?"
                        r"(?:\\s*(?:place|position))?[^$\\d]{0,35}\\$\\s*"
                        r"([0-9][0-9,]*(?:\\.[0-9]{1,2})?)",
                        flags=re.IGNORECASE,
                    )
                    for match in single_pattern.finditer(cleaned):
                        if any(start <= match.start() < end for start, end in occupied):
                            continue
                        _add_payout_range(
                            match.group(1), match.group(1), match.group(2).replace(",", "")
                        )

                def _walk_dk_payout_text(obj):
                    if isinstance(obj, dict):
                        for child in obj.values():
                            _walk_dk_payout_text(child)
                    elif isinstance(obj, list):
                        for child in obj:
                            _walk_dk_payout_text(child)
                    elif isinstance(obj, str) and "$" in obj:
                        _parse_payout_text(obj)

                def _validated_payout_schedule(rows):
                    if not rows:
                        return None, None
                    payout_df = (
                        pd.DataFrame(rows, columns=["Rank", "Prize"])
                        .drop_duplicates("Rank", keep="last")
                        .sort_values("Rank")
                    )
                    if payout_df.empty:
                        return None, None
                    max_rank = int(payout_df["Rank"].max())
                    actual_ranks = set(payout_df["Rank"].astype(int).tolist())
                    if actual_ranks != set(range(1, max_rank + 1)):
                        return None, None
                    schedule = np.zeros(max_rank, dtype=float)
                    schedule[payout_df["Rank"].to_numpy(dtype=int) - 1] = payout_df["Prize"].to_numpy(dtype=float)
                    if np.any(schedule <= 0):
                        return None, None
                    expected_pool = pd.to_numeric(_dk_summary.get("prize_pool"), errors="coerce")
                    if pd.notna(expected_pool) and float(expected_pool) > 0:
                        tolerance = max(1.0, float(expected_pool) * 0.02)
                        if abs(float(schedule.sum()) - float(expected_pool)) > tolerance:
                            return None, None
                    return payout_df, schedule

                _walk_dk_payout_objects(_dk_payload)
                _walk_dk_payout_text(_dk_payload)
                _payout_df, _payout_schedule_auto = _validated_payout_schedule(_payout_rows)
                _payout_source = "DraftKings contest details API"

                # If the JSON does not expose a complete ladder, try the two public
                # contest-detail pages. They sometimes contain the prize table in the
                # rendered/embedded response even when the JSON endpoint only gives a summary.
                if _payout_schedule_auto is None:
                    for _payout_page_url in (
                        f"https://www.draftkings.com/draft/contest/{_contest_id_for_api}",
                        f"https://www.draftkings.com/contest/gamecenter/{_contest_id_for_api}",
                    ):
                        try:
                            _page_response = requests.get(
                                _payout_page_url,
                                headers=_dk_headers,
                                timeout=10,
                            )
                            _page_response.raise_for_status()
                            _page_rows_before = len(_payout_rows)
                            _parse_payout_text(_page_response.text)
                            if len(_payout_rows) > _page_rows_before:
                                _payout_df, _payout_schedule_auto = _validated_payout_schedule(_payout_rows)
                                if _payout_schedule_auto is not None:
                                    _payout_source = "DraftKings public contest page"
                                    break
                        except Exception:
                            continue

                if _payout_schedule_auto is not None:
                    st.session_state["contest_payout_schedule"] = _payout_schedule_auto
                    st.session_state["contest_payout_source_name"] = _payout_source
                    st.session_state["contest_payout_contest_id"] = _contest_id_for_api
                    st.session_state["contest_payout_auto_loaded"] = True
                    st.success(
                        f"DraftKings payout scale loaded automatically: "
                        f"{len(_payout_schedule_auto):,} paid finishing positions."
                    )
                else:
                    st.session_state["contest_payout_auto_loaded"] = False
                    st.info(
                        "DraftKings contest details loaded, but a complete payout ladder was not publicly exposed. "
                        "The app will not guess missing ranks; upload the payout table only for contests where DraftKings blocks it."
                    )
'''

if new in text:
    print("Automatic full DraftKings payout lookup already applied.")
elif old in text:
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
    print("Added automatic full DraftKings payout-scale lookup with completeness validation.")
else:
    raise SystemExit("Could not find DraftKings payout extraction block")
