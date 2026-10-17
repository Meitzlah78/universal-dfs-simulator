from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

old = '''    entry_count = len(entries)\n    lineup_count = len(lineup_ids_df)\n    if lineup_count < entry_count:\n        st.warning(\n            f"You have {entry_count} entries in this contest but only {lineup_count} lineups. "\n            f"Only {lineup_count} existing entries will be updated; build at least {entry_count} lineups to fill them all."\n        )\n    count = min(entry_count, lineup_count)\n    export_df = entries.iloc[:count].copy().reset_index(drop=True)\n    ids = lineup_ids_df.iloc[:count].reset_index(drop=True)\n'''

new = '''    # A replacement export must cover every reserved entry in the selected contest.\n    # Never emit a partial file: any omitted Entry ID would keep its old lineup on DraftKings.\n    entry_ids = entries["Entry ID"].fillna("").astype(str).str.replace(r"\\.0$", "", regex=True).str.strip()\n    invalid_entry_ids = entry_ids.eq("") | entry_ids.str.casefold().eq("nan")\n    if invalid_entry_ids.any():\n        st.error(\n            "The selected DraftKings contest contains one or more blank Entry IDs. "\n            "Re-download the original contest entry CSV before exporting replacements."\n        )\n        return None\n    if entry_ids.duplicated().any():\n        st.error(\n            "The selected DraftKings contest contains duplicate Entry IDs. "\n            "Re-download the original contest entry CSV before exporting replacements."\n        )\n        return None\n\n    entry_count = len(entries)\n    lineup_count = len(lineup_ids_df)\n    if lineup_count < entry_count:\n        st.error(\n            f"Replacement export blocked: this contest has {entry_count} reserved entries but only "\n            f"{lineup_count} new lineups are available. Build at least {entry_count} new lineups so "\n            "every reserved Entry ID is overwritten. No partial replacement file was created."\n        )\n        return None\n\n    # Export exactly one row per reserved Entry ID for this contest. Extra generated\n    # lineups are ignored; no old roster rows or unrelated contest rows are appended.\n    count = entry_count\n    export_df = entries.copy().reset_index(drop=True)\n    export_df["Entry ID"] = entry_ids.reset_index(drop=True)\n    ids = lineup_ids_df.iloc[:entry_count].reset_index(drop=True)\n'''

if new in text:
    print("DK replacement export hardening already applied.")
elif old in text:
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
    print("Hardened DK replacement export to require full reserved-entry coverage.")
else:
    raise SystemExit("Could not find the DK replacement export block to patch safely.")
