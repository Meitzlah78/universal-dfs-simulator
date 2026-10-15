from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel Full Roster only. DraftKings behavior is intentionally untouched.
old = '''_saved_field_key = (
    "classic_contest_field_df"
    if platform == "DraftKings" and lineup_mode == "Classic"
    else "contest_field_df"
)
_saved_field_df = st.session_state.get(_saved_field_key)
_saved_sample_df = st.session_state.get(
    "classic_contest_field_sample_df"
    if platform == "DraftKings" and lineup_mode == "Classic"
    else "contest_field_sample_df"
)'''
new = '''_saved_field_key = (
    "classic_contest_field_df"
    if platform == "DraftKings" and lineup_mode == "Classic"
    else "fd_full_contest_field_df"
    if platform == "FanDuel" and lineup_mode == "Full Roster"
    else "contest_field_df"
)
_saved_field_df = st.session_state.get(_saved_field_key)
_saved_sample_df = st.session_state.get(
    "classic_contest_field_sample_df"
    if platform == "DraftKings" and lineup_mode == "Classic"
    else "fd_full_contest_field_sample_df"
    if platform == "FanDuel" and lineup_mode == "Full Roster"
    else "contest_field_sample_df"
)'''
if old not in text:
    raise SystemExit("saved-field block not found")
text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
