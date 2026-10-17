from pathlib import Path

p = Path('dfs_app.py')
s = p.read_text(encoding='utf-8')
needle = 'st.title("Universal DFS Simulator")\n'
insert = '''st.title("Universal DFS Simulator")

# Completed-contest ingestion for the shared Simmah field-learning model.
with st.expander("Contest History / Field Learning", expanded=False):
    st.caption("Upload completed DraftKings or FanDuel contest standings. Simmah uses these to learn how real fields construct lineups.")
    _hist_files = st.file_uploader(
        "Completed contest standings (CSV or ZIP)",
        type=["csv", "zip"],
        accept_multiple_files=True,
        key="contest_history_uploads",
    )
    _hc1, _hc2, _hc3 = st.columns(3)
    _hist_platform = _hc1.selectbox("Platform", ["Auto", "DraftKings", "FanDuel"], key="history_platform")
    _hist_mode = _hc2.selectbox("Mode", ["Auto", "Classic / Full Roster", "Showdown / Single Game"], key="history_mode")
    _hist_sport = _hc3.selectbox("Sport", ["NFL", "NBA", "WNBA", "MMA", "NASCAR"], key="history_sport")
    if "contest_history_registry" not in st.session_state:
        st.session_state["contest_history_registry"] = []
    if _hist_files and st.button("LEARN FROM CONTESTS", key="learn_contest_history", use_container_width=True):
        import io as _io
        import zipfile as _zipfile
        import hashlib as _hashlib
        _learned = 0
        _rows = 0
        for _f in _hist_files:
            _raw = _f.getvalue()
            _digest = _hashlib.sha256(_raw).hexdigest()
            if any(x.get("sha256") == _digest for x in st.session_state["contest_history_registry"]):
                continue
            _frames = []
            try:
                if _f.name.lower().endswith(".zip"):
                    with _zipfile.ZipFile(_io.BytesIO(_raw)) as _zf:
                        for _name in _zf.namelist():
                            if _name.lower().endswith(".csv"):
                                with _zf.open(_name) as _fh:
                                    _frames.append(pd.read_csv(_fh, low_memory=False))
                else:
                    _frames.append(pd.read_csv(_io.BytesIO(_raw), low_memory=False))
            except Exception as _exc:
                st.warning(f"Could not read {_f.name}: {_exc}")
                continue
            _count = int(sum(len(x) for x in _frames))
            if not _count:
                continue
            _columns = sorted({str(c) for df in _frames for c in df.columns})
            _platform = _hist_platform
            if _platform == "Auto":
                _joined = " ".join(_columns).lower()
                _platform = "DraftKings" if ("entryid" in _joined or "lineup" in _joined) else "Unknown"
            _mode = _hist_mode
            if _mode == "Auto":
                _joined = " ".join(_columns).lower()
                _mode = "Showdown / Single Game" if ("captain" in _joined or "mvp" in _joined) else "Classic / Full Roster"
            st.session_state["contest_history_registry"].append({
                "name": _f.name,
                "sha256": _digest,
                "platform": _platform,
                "mode": _mode,
                "sport": _hist_sport,
                "lineups": _count,
                "columns": _columns,
            })
            _learned += 1
            _rows += _count
        if _learned:
            st.success(f"Learned {_learned} contest file(s) containing {_rows:,} rows.")
        else:
            st.info("No new contest files were added.")
    _registry = st.session_state.get("contest_history_registry", [])
    if _registry:
        _total_rows = sum(int(x.get("lineups", 0)) for x in _registry)
        st.caption(f"This session: {len(_registry)} contest file(s) · {_total_rows:,} rows available for field learning")
'''
if needle not in s:
    raise SystemExit('title anchor not found')
s = s.replace(needle, insert, 1)
p.write_text(s, encoding='utf-8')
