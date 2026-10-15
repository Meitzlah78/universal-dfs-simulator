from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel Full Roster only. DraftKings behavior is intentionally untouched.
old_salary = '''        fd_salary_range = st.slider(
            "Allowed lineup salary range",
            min_value=0,
            max_value=60000,
            value=(54000, 60000),
            step=100,
            format="$%d",
            key="fd_build_salary_range_" + lineup_mode.replace(" ", "_").lower(),
            help="Only build lineups whose total salary falls inside this range."
        )'''
new_salary = '''        fd_salary_range = st.slider(
            "Allowed lineup salary range",
            min_value=0,
            max_value=60000,
            value=(57000, 60000) if lineup_mode == "Full Roster" else (54000, 60000),
            step=100,
            format="$%d",
            key="fd_build_salary_range_" + lineup_mode.replace(" ", "_").lower(),
            help="Only build lineups whose total salary falls inside this range."
        )'''
if old_salary in text:
    text = text.replace(old_salary, new_salary, 1)
elif new_salary not in text:
    raise SystemExit("FanDuel salary slider block not found")

old_stack = '''            default=["QB + 2 teammates + bring-back"],
            key="fd_full_roster_stack_rules",'''
new_stack = '''            default=["No stack rule"],
            key="fd_full_roster_stack_rules",'''
if old_stack in text:
    text = text.replace(old_stack, new_stack, 1)
elif new_stack not in text:
    raise SystemExit("FanDuel Full Roster stack default block not found")

helper_anchor = '''if platform == "FanDuel":
    # One-upload FanDuel slate setup.'''
helper_code = '''def fetch_fanduel_contest_details(contest_id):
    """Best-effort public FanDuel contest lookup. Never requires user credentials."""
    contest_id = str(contest_id or "").strip()
    if not contest_id:
        return None
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    }
    urls = [
        f"https://api.fanduel.com/contests/{contest_id}",
        f"https://api.fanduel.com/contests?contest={contest_id}",
        f"https://api.fanduel.com/contests?id={contest_id}",
    ]
    for url in urls:
        try:
            response = requests.get(url, headers=headers, timeout=8)
            if response.status_code != 200:
                continue
            payload = response.json()
            candidates = []
            if isinstance(payload, dict):
                if isinstance(payload.get("contests"), list):
                    candidates.extend(payload["contests"])
                candidates.append(payload)
            elif isinstance(payload, list):
                candidates.extend(payload)
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                item_id = str(item.get("id", item.get("contest_id", ""))).strip()
                if item_id and item_id != contest_id:
                    continue
                size = item.get("size", {}) if isinstance(item.get("size"), dict) else {}
                prizes = item.get("prizes", {}) if isinstance(item.get("prizes"), dict) else {}
                details = {
                    "field_size": item.get("max_size") or size.get("max") or item.get("size_max"),
                    "current_entries": item.get("entry_count") or item.get("entries_count") or item.get("open_count"),
                    "max_entries_per_user": item.get("max_entries_per_user"),
                    "prize_pool": prizes.get("total") or item.get("prize_pool") or item.get("prize_total"),
                    "prize_summary": prizes.get("summary") or item.get("prize_summary"),
                    "raw": item,
                }
                if any(details.get(k) not in (None, "", 0) for k in ("field_size", "current_entries", "max_entries_per_user", "prize_pool", "prize_summary")):
                    return details
        except Exception:
            continue
    return None


if platform == "FanDuel":
    # One-upload FanDuel slate setup.'''
if "def fetch_fanduel_contest_details(contest_id):" not in text:
    if helper_anchor not in text:
        raise SystemExit("FanDuel setup anchor not found")
    text = text.replace(helper_anchor, helper_code, 1)

old_selected = '''                st.session_state["selected_fd_contest"] = {
                    "id": str(fd_selected_row[fd_id_col]),
                    "name": str(fd_selected_row[fd_name_col]),
                    "your_entries": int(fd_selected_row["Entries"]),
                    "entry_fee": float(fd_fee) if pd.notna(fd_fee) else None,
                }
                fd_fee_text = f"${float(fd_fee):.2f}" if pd.notna(fd_fee) else "not listed"
                st.success(
                    f"Selected: {fd_selected_row[fd_name_col]} | Contest ID: {fd_selected_row[fd_id_col]} | "
                    f"Your entries: {int(fd_selected_row['Entries'])} | Entry fee: {fd_fee_text}"
                )
                st.caption(
                    "The entry file identifies your contest and entries. Opponent lineups and payouts are simulated, not taken from actual contest results."
                )'''
new_selected = '''                _fd_contest_id = str(fd_selected_row[fd_id_col])
                _fd_auto_details = fetch_fanduel_contest_details(_fd_contest_id)
                st.session_state["selected_fd_contest"] = {
                    "id": _fd_contest_id,
                    "name": str(fd_selected_row[fd_name_col]),
                    "your_entries": int(fd_selected_row["Entries"]),
                    "entry_fee": float(fd_fee) if pd.notna(fd_fee) else None,
                    "field_size": (_fd_auto_details or {}).get("field_size"),
                    "current_entries": (_fd_auto_details or {}).get("current_entries"),
                    "max_entries_per_user": (_fd_auto_details or {}).get("max_entries_per_user"),
                    "prize_pool": (_fd_auto_details or {}).get("prize_pool"),
                    "prize_summary": (_fd_auto_details or {}).get("prize_summary"),
                }
                fd_fee_text = f"${float(fd_fee):.2f}" if pd.notna(fd_fee) else "not listed"
                st.success(
                    f"Selected: {fd_selected_row[fd_name_col]} | Contest ID: {_fd_contest_id} | "
                    f"Your entries: {int(fd_selected_row['Entries'])} | Entry fee: {fd_fee_text}"
                )
                if _fd_auto_details:
                    _fd_bits = []
                    if _fd_auto_details.get("field_size"):
                        _fd_bits.append(f"Field size: {int(_fd_auto_details['field_size']):,}")
                    if _fd_auto_details.get("max_entries_per_user"):
                        _fd_bits.append(f"Max entries/user: {int(_fd_auto_details['max_entries_per_user']):,}")
                    if _fd_auto_details.get("prize_pool"):
                        _fd_bits.append(f"Prize pool: ${float(_fd_auto_details['prize_pool']):,.2f}")
                    if _fd_auto_details.get("prize_summary"):
                        _fd_bits.append(f"Prizes: {_fd_auto_details['prize_summary']}")
                    st.info("FanDuel contest lookup: " + (" | ".join(_fd_bits) if _fd_bits else "contest found"))
                else:
                    st.caption(
                        "FanDuel contest ID, name, fee, and your entries were loaded from the CSV. "
                        "FanDuel did not expose the full field size/payout details publicly for this contest, so those details cannot be verified automatically yet."
                    )'''
if old_selected in text:
    text = text.replace(old_selected, new_selected, 1)
elif "_fd_auto_details = fetch_fanduel_contest_details" not in text:
    raise SystemExit("FanDuel selected contest block not found")

path.write_text(text, encoding="utf-8")
