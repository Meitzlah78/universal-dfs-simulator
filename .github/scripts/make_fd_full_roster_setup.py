from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel only. DraftKings is intentionally untouched.
# FanDuel's official entry template uses underscore-style names such as
# contest_name, contest_id, entry_id, and entry_fee.
needle = '''            fd_name_col = next((fd_entry_lookup[k] for k in ("contest name", "contest") if k in fd_entry_lookup), None)
            fd_id_col = next((fd_entry_lookup[k] for k in ("contest id", "contestid", "contest_id") if k in fd_entry_lookup), None)
            fd_entries_col = next((fd_entry_lookup[k] for k in ("entry id", "entryid", "entry_id") if k in fd_entry_lookup), None)
            fd_fee_col = next((fd_entry_lookup[k] for k in ("entry fee", "entryfee", "entry_fee", "fee") if k in fd_entry_lookup), None)
'''
replacement = '''            fd_name_col = next((fd_entry_lookup[k] for k in (
                "contest name", "contest_name", "contestname", "contest"
            ) if k in fd_entry_lookup), None)
            fd_id_col = next((fd_entry_lookup[k] for k in (
                "contest id", "contest_id", "contestid"
            ) if k in fd_entry_lookup), None)
            fd_entries_col = next((fd_entry_lookup[k] for k in (
                "entry id", "entry_id", "entryid"
            ) if k in fd_entry_lookup), None)
            fd_fee_col = next((fd_entry_lookup[k] for k in (
                "entry fee", "entry_fee", "entryfee", "fee"
            ) if k in fd_entry_lookup), None)
'''
if needle not in text:
    raise SystemExit("FanDuel contest selector column block not found")
text = text.replace(needle, replacement, 1)
path.write_text(text, encoding="utf-8")
