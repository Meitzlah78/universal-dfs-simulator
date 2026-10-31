from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

old_dk = '''    field_ownership_display = st.session_state.get("latest_field_ownership")
    if (
        isinstance(field_ownership_display, pd.DataFrame)
        and not field_ownership_display.empty
        and "Name" in field_ownership_display.columns
        and "Ownership %" in field_ownership_display.columns
    ):
'''
new_dk = '''    # Prefer field ownership saved for the active format. If that table is missing,
    # rebuild it directly from the current simulated opponent field so the Player Pool
    # always shows field ownership after CONTEST SIM.
    _ownership_by_format = st.session_state.get("latest_field_ownership_by_format", {})
    field_ownership_display = (
        _ownership_by_format.get(selected_format)
        if isinstance(_ownership_by_format, dict)
        else None
    )
    if not isinstance(field_ownership_display, pd.DataFrame) or field_ownership_display.empty:
        field_ownership_display = st.session_state.get("latest_field_ownership")

    if not isinstance(field_ownership_display, pd.DataFrame) or field_ownership_display.empty:
        if platform == "DraftKings" and lineup_mode == "Showdown":
            _active_field = st.session_state.get("contest_field_df")
            _role_col = "Captain"
            _field_slots = [c for c in ["Captain", "Flex1", "Flex2", "Flex3", "Flex4", "Flex5"] if isinstance(_active_field, pd.DataFrame) and c in _active_field.columns]
        else:
            _active_field = st.session_state.get("classic_contest_field_df")
            _role_col = None
            _field_slots = [c for c in ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"] if isinstance(_active_field, pd.DataFrame) and c in _active_field.columns]

        if isinstance(_active_field, pd.DataFrame) and not _active_field.empty and _field_slots:
            _field_total = len(_active_field)
            _all_counts = (
                _active_field[_field_slots]
                .astype(str)
                .apply(lambda row: pd.unique(row.str.strip()).tolist(), axis=1)
                .explode()
                .value_counts()
            )
            _field_names = player_display["Name"].astype(str).str.strip()
            field_ownership_display = pd.DataFrame({
                "Name": _field_names,
                "Ownership %": _field_names.map(lambda n: 100.0 * _all_counts.get(n, 0) / max(_field_total, 1)),
            })
            if _role_col is not None and _role_col in _active_field.columns:
                _role_counts = _active_field[_role_col].astype(str).str.strip().value_counts()
                field_ownership_display["Captain/MVP Ownership %"] = _field_names.map(
                    lambda n: 100.0 * _role_counts.get(n, 0) / max(_field_total, 1)
                )
            if not isinstance(_ownership_by_format, dict):
                _ownership_by_format = {}
            _ownership_by_format[selected_format] = field_ownership_display.copy()
            st.session_state["latest_field_ownership_by_format"] = _ownership_by_format
            st.session_state["latest_field_ownership"] = field_ownership_display.copy()

    if (
        isinstance(field_ownership_display, pd.DataFrame)
        and not field_ownership_display.empty
        and "Name" in field_ownership_display.columns
        and "Ownership %" in field_ownership_display.columns
    ):
'''

if old_dk in text:
    text = text.replace(old_dk, new_dk, 1)
elif new_dk not in text:
    raise SystemExit("Could not find DraftKings field ownership display block")

old_fd = '''    fd_ownership_by_format = st.session_state.get("latest_field_ownership_by_format", {})
    fd_visible_field = fd_ownership_by_format.get(selected_format) if isinstance(fd_ownership_by_format, dict) else None
    if isinstance(fd_visible_field, pd.DataFrame) and not fd_visible_field.empty and "Name" in fd_visible_field.columns:
'''
new_fd = '''    fd_ownership_by_format = st.session_state.get("latest_field_ownership_by_format", {})
    fd_visible_field = fd_ownership_by_format.get(selected_format) if isinstance(fd_ownership_by_format, dict) else None

    # Rebuild missing FanDuel field ownership directly from this format's simulated
    # opponent field. Single Game keeps MVP and FLEX ownership separate.
    if not isinstance(fd_visible_field, pd.DataFrame) or fd_visible_field.empty:
        _fd_field_key = "fd_contest_field_" + lineup_mode.replace(" ", "_").lower()
        _fd_active_field = st.session_state.get(_fd_field_key)
        if lineup_mode == "Single Game":
            _fd_role_col = "MVP"
            _fd_field_slots = [c for c in ["MVP", "FLEX1", "FLEX2", "FLEX3", "FLEX4", "FLEX5"] if isinstance(_fd_active_field, pd.DataFrame) and c in _fd_active_field.columns]
        else:
            _fd_role_col = None
            _fd_field_slots = [c for c in ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "D"] if isinstance(_fd_active_field, pd.DataFrame) and c in _fd_active_field.columns]

        if isinstance(_fd_active_field, pd.DataFrame) and not _fd_active_field.empty and _fd_field_slots:
            _fd_field_total = len(_fd_active_field)
            _fd_all_counts = (
                _fd_active_field[_fd_field_slots]
                .astype(str)
                .apply(lambda row: pd.unique(row.str.strip()).tolist(), axis=1)
                .explode()
                .value_counts()
            )
            _fd_field_names = fd_player_display["Name"].astype(str).str.strip()
            fd_visible_field = pd.DataFrame({
                "Name": _fd_field_names,
                "Ownership %": _fd_field_names.map(lambda n: 100.0 * _fd_all_counts.get(n, 0) / max(_fd_field_total, 1)),
            })
            if _fd_role_col is not None and _fd_role_col in _fd_active_field.columns:
                _fd_role_counts = _fd_active_field[_fd_role_col].astype(str).str.strip().value_counts()
                fd_visible_field["Captain/MVP Ownership %"] = _fd_field_names.map(
                    lambda n: 100.0 * _fd_role_counts.get(n, 0) / max(_fd_field_total, 1)
                )
            if not isinstance(fd_ownership_by_format, dict):
                fd_ownership_by_format = {}
            fd_ownership_by_format[selected_format] = fd_visible_field.copy()
            st.session_state["latest_field_ownership_by_format"] = fd_ownership_by_format

    if isinstance(fd_visible_field, pd.DataFrame) and not fd_visible_field.empty and "Name" in fd_visible_field.columns:
'''

if old_fd in text:
    text = text.replace(old_fd, new_fd, 1)
elif new_fd not in text:
    raise SystemExit("Could not find FanDuel field ownership display block")

path.write_text(text, encoding="utf-8")
print("Player Pool field ownership now rebuilds from the active opponent field for all four formats.")
