from pathlib import Path

APP = Path("dfs_app.py")
text = APP.read_text(encoding="utf-8")


def replace_once(old, new, label):
    global text
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"Patch anchor not found: {label}")
    text = text.replace(old, new, 1)


# Add a cached DraftKings contest-details loader before contest target sizing.
replace_once(
'''def get_contest_opponent_target(platform_key, default=MAX_SIMULATED_OPPONENTS):
''',
'''@st.cache_data(show_spinner=False, ttl=300)
def fetch_draftkings_contest_size(contest_id):
    """Best-effort DraftKings contest entry count lookup from the public contest API."""
    contest_id = str(contest_id or "").strip()
    if not contest_id.isdigit():
        return None, None
    url = f"https://api.draftkings.com/contests/v1/contests/{contest_id}?format=json"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0 Safari/537.36"
        )
    }
    try:
        response = requests.get(url, headers=headers, timeout=(4, 10))
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return None, None

    current_keys = {
        "entries", "entrycount", "entriescount", "currententries",
        "numberofentries", "currententrycount", "contestentrycount",
    }
    max_keys = {
        "maxentries", "maximumentries", "maximumnumberofentries",
        "contestcapacity", "capacity", "totalentries",
    }

    current_values = []
    max_values = []

    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = "".join(ch for ch in str(key).casefold() if ch.isalnum())
                if normalized in current_keys:
                    parsed = pd.to_numeric(item, errors="coerce")
                    if pd.notna(parsed) and float(parsed) > 0:
                        current_values.append(int(float(parsed)))
                if normalized in max_keys:
                    parsed = pd.to_numeric(item, errors="coerce")
                    if pd.notna(parsed) and float(parsed) > 0:
                        max_values.append(int(float(parsed)))
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)
    current_entries = max(current_values) if current_values else None
    max_entries = max(max_values) if max_values else None
    return current_entries, max_entries


def get_contest_opponent_target(platform_key, default=MAX_SIMULATED_OPPONENTS):
''',
"DraftKings contest size helper",
)


replace_once(
'''    # The sampled opponent field is used to estimate the full contest, not to
    # pretend the sample is the actual contest size.
    previous_field_size = active_dk_selection.get("field_size")
    try:
        default_field_size = int(previous_field_size) if previous_field_size else 45396
    except (TypeError, ValueError):
        default_field_size = 45396
    active_field_size = st.number_input(
        "Current total contest entries (update from DraftKings lobby)",
        min_value=2,
        max_value=200000,
        value=max(2, min(200000, default_field_size)),
        step=100,
        key=f"dk_field_size_{dk_slate_key}",
        help="Enter the current total entries shown in the DraftKings lobby, including your entries."
    )
    active_dk_selection["field_size"] = int(active_field_size)
''',
'''    # Pull the current contest size automatically from DraftKings when available.
    # Keep the manual input only as a fallback if DraftKings does not return usable details.
    previous_field_size = active_dk_selection.get("field_size")
    auto_current_entries, auto_max_entries = fetch_draftkings_contest_size(
        active_dk_selection.get("id")
    )
    auto_field_size = auto_current_entries or auto_max_entries
    try:
        fallback_field_size = int(previous_field_size) if previous_field_size else 45396
    except (TypeError, ValueError):
        fallback_field_size = 45396

    if auto_field_size is not None and int(auto_field_size) >= 2:
        active_field_size = int(auto_field_size)
        if auto_current_entries:
            st.success(f"Contest field size loaded automatically from DraftKings: {active_field_size:,} entries")
        else:
            st.success(f"Contest capacity loaded automatically from DraftKings: {active_field_size:,} entries")
        if auto_current_entries and auto_max_entries and auto_max_entries >= auto_current_entries:
            st.caption(f"Current entries: {auto_current_entries:,} of {auto_max_entries:,} maximum")
    else:
        active_field_size = st.number_input(
            "Contest field size (fallback only)",
            min_value=2,
            max_value=200000,
            value=max(2, min(200000, fallback_field_size)),
            step=100,
            key=f"dk_field_size_{dk_slate_key}",
            help="DraftKings contest details could not be loaded automatically, so enter the current total entries shown in the lobby."
        )
        st.caption("SIMMAH will use this manual field size only when the DraftKings contest lookup is unavailable.")

    active_dk_selection["field_size"] = int(active_field_size)
''',
"automatic DK field size",
)

APP.write_text(text, encoding="utf-8")
print("Patched automatic contest field size")
