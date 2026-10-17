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


replace_once(
'''format_options = {
    "DraftKings Classic": ("DraftKings", "Classic"),
    "DraftKings Showdown": ("DraftKings", "Showdown"),
    "FanDuel Full Roster": ("FanDuel", "Full Roster"),
    "FanDuel Single Game": ("FanDuel", "Single Game"),
}
selected_format = st.selectbox(
    "Format",
    list(format_options.keys()),
    key="dfs_format",
)
''',
'''format_options = {
    "DraftKings Classic": ("DraftKings", "Classic"),
    "DraftKings Showdown": ("DraftKings", "Showdown"),
    "FanDuel Full Roster": ("FanDuel", "Full Roster"),
    "FanDuel Single Game": ("FanDuel", "Single Game"),
}


def detect_uploaded_dfs_format(uploaded_file):
    """Detect DK/FD and single-game/full-roster from an entries/slate CSV."""
    import csv
    import io

    if uploaded_file is None:
        return None
    try:
        uploaded_file.seek(0)
        raw_text = uploaded_file.getvalue().decode("utf-8-sig", errors="replace")
        rows = list(csv.reader(io.StringIO(raw_text)))
        uploaded_file.seek(0)
    except Exception:
        return None
    if not rows:
        return None

    # The first entry-table header is the most reliable place to identify roster type.
    header = [str(cell).strip().upper() for cell in rows[0]]
    header_set = set(header)

    # FanDuel exports use MVP / AnyFLEX wording for single-game and commonly use
    # D rather than DST in full-roster templates.
    is_fd_single = any("MVP" in cell for cell in header) or any("ANYFLEX" in cell for cell in header)
    if is_fd_single:
        return "FanDuel Single Game"

    # DraftKings Showdown entries use CPT plus FLEX slots.
    if "CPT" in header_set:
        return "DraftKings Showdown"

    # Distinguish the full-roster sites using their roster headers and player-table wording.
    all_text = raw_text[:20000].upper()
    if "NICKNAME" in all_text or "FANDUEL" in all_text:
        return "FanDuel Full Roster"
    if "D" in header_set and "DST" not in header_set and "DEF" not in header_set:
        return "FanDuel Full Roster"

    # DK My Contests / lineup templates use DST and the salary table commonly has
    # Name + ID, AvgPointsPerGame, or TeamAbbrev.
    if (
        "DST" in header_set
        or "AVGPOINTSPERGAME" in all_text
        or "TEAMABBREV" in all_text
        or "NAME + ID" in all_text
        or "DRAFTKINGS" in all_text
    ):
        return "DraftKings Classic"

    return None


st.write("### Slate Setup")
st.caption("Upload your DraftKings or FanDuel entries/slate CSV once. SIMMAH will choose the site and format automatically.")
auto_slate_file = st.file_uploader(
    "Upload Entries / Slate CSV",
    type=["csv"],
    key="universal_slate_setup_file",
)

if auto_slate_file is not None:
    detected_format = detect_uploaded_dfs_format(auto_slate_file)
    if detected_format:
        if st.session_state.get("dfs_format") != detected_format:
            st.session_state["dfs_format"] = detected_format
            st.session_state["auto_detected_dfs_format"] = detected_format
            st.rerun()
        st.success(f"Format detected automatically: {detected_format}")
    else:
        st.warning("SIMMAH could not identify this entries file automatically. Choose the format below and the file will still be used.")

selected_format = st.selectbox(
    "Format",
    list(format_options.keys()),
    key="dfs_format",
)
''',
"universal format detector",
)

replace_once(
'''    fd_slate_file = st.file_uploader(
        "Upload FanDuel Slate / Entries CSV",
        type=["csv"],
        key="fd_slate_setup_file",
        help="Use the FanDuel CSV that contains your contest entries and player reference table."
    )
    fd_file = fd_slate_file
    fd_entry_file = fd_slate_file
''',
'''    if auto_slate_file is not None:
        fd_slate_file = auto_slate_file
        st.caption("Using the slate file uploaded above.")
    else:
        fd_slate_file = st.file_uploader(
            "Upload FanDuel Slate / Entries CSV",
            type=["csv"],
            key="fd_slate_setup_file",
            help="Use the FanDuel CSV that contains your contest entries and player reference table."
        )
    fd_file = fd_slate_file
    fd_entry_file = fd_slate_file
''',
"reuse universal FD upload",
)

replace_once(
'''    dk_slate_file = st.file_uploader(
        "Upload DraftKings Slate / Entries CSV",
        type=["csv"],
        key="dk_slate_setup_file",
        help="Use the original DraftKings My Contests CSV for this slate. No separate salary upload is needed."
    )
    salary_file = dk_slate_file
    entry_file = dk_slate_file
''',
'''    if auto_slate_file is not None:
        dk_slate_file = auto_slate_file
        st.caption("Using the slate file uploaded above.")
    else:
        dk_slate_file = st.file_uploader(
            "Upload DraftKings Slate / Entries CSV",
            type=["csv"],
            key="dk_slate_setup_file",
            help="Use the original DraftKings My Contests CSV for this slate. No separate salary upload is needed."
        )
    salary_file = dk_slate_file
    entry_file = dk_slate_file
''',
"reuse universal DK upload",
)

APP.write_text(text, encoding="utf-8")
print("Patched automatic DFS format detection")
