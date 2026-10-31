from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

old = '''            _key = normalize_projection_player_name(_name)
            _matches = _fd_hist_index.get(_key, [])
            if not _matches:
                continue
            _rows = _fd_hist.loc[_matches].copy() if all(isinstance(x, (int, np.integer)) for x in _matches) else pd.DataFrame()
            if _rows.empty:
                continue'''
new = '''            _key = normalize_projection_player_name(_name)
            _matched_history = _fd_hist_index.get(_key)
            if _matched_history is None or not isinstance(_matched_history, pd.DataFrame) or _matched_history.empty:
                continue
            _rows = _matched_history.copy()
            if _rows.empty:
                continue'''
if old not in text:
    raise SystemExit("QB historical-role anchor not found")
text = text.replace(old, new, 1)

old = '''                _matches = _fd_hist_index.get(normalize_projection_player_name(_name), [])
                if not _matches or not all(isinstance(x, (int, np.integer)) for x in _matches):
                    continue
                _rows = _fd_hist.loc[_matches].copy()
                if _rows.empty:
                    continue'''
new = '''                _matched_history = _fd_hist_index.get(normalize_projection_player_name(_name))
                if _matched_history is None or not isinstance(_matched_history, pd.DataFrame) or _matched_history.empty:
                    continue
                _rows = _matched_history.copy()
                if _rows.empty:
                    continue'''
if old not in text:
    raise SystemExit("Shared PBP historical-role anchor not found")
text = text.replace(old, new, 1)

# Rename internal FD-prefixed role variables to shared names only where doing so
# is safe and local to the PBP engine. This makes future DK/FD fixes land in one place.
text = text.replace("# FanDuel PBP role inputs:", "# Shared NFL PBP role inputs:", 1)

path.write_text(text, encoding="utf-8")
print("Fixed shared PBP historical role lookup")
