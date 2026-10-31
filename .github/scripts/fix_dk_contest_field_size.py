from pathlib import Path

APP = Path("dfs_app.py")
text = APP.read_text(encoding="utf-8")

old = '''    auto_current_entries, auto_max_entries = fetch_draftkings_contest_size(
        active_dk_selection.get("id")
    )
    auto_field_size = auto_current_entries or auto_max_entries
'''
new = '''    auto_current_entries, auto_max_entries = fetch_draftkings_contest_size(
        active_dk_selection.get("id")
    )
    # Pregame contest simulation should use the contest capacity when DraftKings
    # provides it. Using current entries while a contest is still filling makes
    # estimated ranks, cash rates, payouts, and ROI too optimistic.
    auto_field_size = auto_max_entries or auto_current_entries
'''

if new not in text:
    if old not in text:
        raise SystemExit("DK contest field-size anchor not found")
    text = text.replace(old, new, 1)

old_message = '''    if auto_field_size is not None and int(auto_field_size) >= 2:
        active_field_size = int(auto_field_size)
        if auto_current_entries:
            st.success(f"Contest field size loaded automatically from DraftKings: {active_field_size:,} entries")
        else:
            st.success(f"Contest capacity loaded automatically from DraftKings: {active_field_size:,} entries")
        if auto_current_entries and auto_max_entries and auto_max_entries >= auto_current_entries:
            st.caption(f"Current entries: {auto_current_entries:,} of {auto_max_entries:,} maximum")
'''
new_message = '''    if auto_field_size is not None and int(auto_field_size) >= 2:
        active_field_size = int(auto_field_size)
        if auto_max_entries:
            st.success(f"Contest capacity loaded automatically from DraftKings: {active_field_size:,} entries")
        else:
            st.success(f"Contest field size loaded automatically from DraftKings: {active_field_size:,} entries")
        if auto_current_entries and auto_max_entries and auto_max_entries >= auto_current_entries:
            st.caption(f"Current entries: {auto_current_entries:,} of {auto_max_entries:,} maximum. Pregame ROI uses the maximum field size.")
'''

if new_message not in text:
    if old_message not in text:
        raise SystemExit("DK contest field-size status anchor not found")
    text = text.replace(old_message, new_message, 1)

APP.write_text(text, encoding="utf-8")
print("DraftKings contest simulation now prefers maximum field size before lock")
