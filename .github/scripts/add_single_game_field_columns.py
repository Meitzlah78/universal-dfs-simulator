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


# DraftKings: Showdown should display CPT and FLEX field ownership separately.
replace_once(
'''    # Add simulated opponent-field ownership beside the user's own exposure columns.
    # The field table is created during Contest Sim and retained in session state.
    field_ownership_display = st.session_state.get("latest_field_ownership")
    if (
        isinstance(field_ownership_display, pd.DataFrame)
        and not field_ownership_display.empty
        and "Name" in field_ownership_display.columns
        and "Ownership %" in field_ownership_display.columns
    ):
        field_own_map = dict(zip(
            field_ownership_display["Name"].astype(str).str.strip(),
            pd.to_numeric(field_ownership_display["Ownership %"], errors="coerce")
        ))
        player_display["Field Own %"] = player_display["Name"].astype(str).str.strip().map(field_own_map).round(1)
        if "Captain/MVP Ownership %" in field_ownership_display.columns and not (
            platform == "DraftKings" and lineup_mode == "Classic"
        ):
            field_captain_map = dict(zip(
                field_ownership_display["Name"].astype(str).str.strip(),
                pd.to_numeric(field_ownership_display["Captain/MVP Ownership %"], errors="coerce")
            ))
            player_display["Field CPT Own %"] = player_display["Name"].astype(str).str.strip().map(field_captain_map).round(1)
    else:
        player_display["Field Own %"] = np.nan
        if not (platform == "DraftKings" and lineup_mode == "Classic"):
            player_display["Field CPT Own %"] = np.nan
''',
'''    # Add simulated opponent-field ownership beside the user's own exposure columns.
    # Full-roster formats use overall ownership. Single-game formats show special-slot
    # and FLEX ownership separately so the Player Pool mirrors how the field actually builds.
    field_ownership_display = st.session_state.get("latest_field_ownership")
    if (
        isinstance(field_ownership_display, pd.DataFrame)
        and not field_ownership_display.empty
        and "Name" in field_ownership_display.columns
        and "Ownership %" in field_ownership_display.columns
    ):
        field_own_map = dict(zip(
            field_ownership_display["Name"].astype(str).str.strip(),
            pd.to_numeric(field_ownership_display["Ownership %"], errors="coerce")
        ))
        names_for_field = player_display["Name"].astype(str).str.strip()
        overall_field = names_for_field.map(field_own_map)
        if platform == "DraftKings" and lineup_mode == "Showdown":
            if "Captain/MVP Ownership %" in field_ownership_display.columns:
                field_captain_map = dict(zip(
                    field_ownership_display["Name"].astype(str).str.strip(),
                    pd.to_numeric(field_ownership_display["Captain/MVP Ownership %"], errors="coerce")
                ))
                captain_field = names_for_field.map(field_captain_map).fillna(0.0)
            else:
                captain_field = pd.Series(0.0, index=player_display.index)
            player_display["Field CPT Own %"] = captain_field.round(1)
            player_display["Field FLEX Own %"] = (overall_field.fillna(0.0) - captain_field).clip(lower=0.0).round(1)
            player_display = player_display.drop(columns=["Field Own %"], errors="ignore")
        else:
            player_display["Field Own %"] = overall_field.round(1)
            player_display = player_display.drop(columns=["Field CPT Own %", "Field FLEX Own %"], errors="ignore")
    else:
        if platform == "DraftKings" and lineup_mode == "Showdown":
            player_display["Field CPT Own %"] = np.nan
            player_display["Field FLEX Own %"] = np.nan
            player_display = player_display.drop(columns=["Field Own %"], errors="ignore")
        else:
            player_display["Field Own %"] = np.nan
            player_display = player_display.drop(columns=["Field CPT Own %", "Field FLEX Own %"], errors="ignore")
''',
"DK single-game field columns",
)

# FanDuel: show MVP/FLEX field ownership in the visible Single Game Player Pool.
replace_once(
'''        else:
            fd_player_display["Exposure %"] = np.nan
            if lineup_mode == "Single Game":
                fd_player_display["MVP Exp %"] = np.nan
                fd_player_display["Flex Exp %"] = np.nan
            else:
                fd_player_display = fd_player_display.drop(
                    columns=["MVP Exp %", "Flex Exp %"], errors="ignore"
                )

        fd_snapshot_display = fd_player_display.copy()
''',
'''        else:
            fd_player_display["Exposure %"] = np.nan
            if lineup_mode == "Single Game":
                fd_player_display["MVP Exp %"] = np.nan
                fd_player_display["Flex Exp %"] = np.nan
            else:
                fd_player_display = fd_player_display.drop(
                    columns=["MVP Exp %", "Flex Exp %"], errors="ignore"
                )

        # Put simulated field ownership directly in the visible FanDuel Player Pool.
        fd_ownership_by_format = st.session_state.get("latest_field_ownership_by_format", {})
        fd_visible_field = fd_ownership_by_format.get(selected_format) if isinstance(fd_ownership_by_format, dict) else None
        if isinstance(fd_visible_field, pd.DataFrame) and not fd_visible_field.empty and "Name" in fd_visible_field.columns:
            fd_names_for_field = fd_player_display["Name"].astype(str).str.strip()
            fd_overall_map = dict(zip(
                fd_visible_field["Name"].astype(str).str.strip(),
                pd.to_numeric(fd_visible_field.get("Ownership %"), errors="coerce")
            ))
            fd_overall = fd_names_for_field.map(fd_overall_map)
            if lineup_mode == "Single Game":
                if "Captain/MVP Ownership %" in fd_visible_field.columns:
                    fd_mvp_map = dict(zip(
                        fd_visible_field["Name"].astype(str).str.strip(),
                        pd.to_numeric(fd_visible_field["Captain/MVP Ownership %"], errors="coerce")
                    ))
                    fd_mvp = fd_names_for_field.map(fd_mvp_map).fillna(0.0)
                else:
                    fd_mvp = pd.Series(0.0, index=fd_player_display.index)
                fd_player_display["Field MVP Own %"] = fd_mvp.round(1)
                fd_player_display["Field FLEX Own %"] = (fd_overall.fillna(0.0) - fd_mvp).clip(lower=0.0).round(1)
                fd_player_display = fd_player_display.drop(columns=["Field Own %"], errors="ignore")
            else:
                fd_player_display["Field Own %"] = fd_overall.round(1)
                fd_player_display = fd_player_display.drop(columns=["Field MVP Own %", "Field FLEX Own %"], errors="ignore")
        else:
            if lineup_mode == "Single Game":
                fd_player_display["Field MVP Own %"] = np.nan
                fd_player_display["Field FLEX Own %"] = np.nan
                fd_player_display = fd_player_display.drop(columns=["Field Own %"], errors="ignore")
            else:
                fd_player_display["Field Own %"] = np.nan
                fd_player_display = fd_player_display.drop(columns=["Field MVP Own %", "Field FLEX Own %"], errors="ignore")

        fd_snapshot_display = fd_player_display.copy()
''',
"FD single-game field columns",
)

APP.write_text(text, encoding="utf-8")
print("Patched single-game CPT/MVP and FLEX field ownership columns")
