"""Player exposure for the entries in the displayed assigned portfolio."""
from collections import Counter

import pandas as pd


def player_exposure(lineups, slots, special_role=None):
    """Count entries containing each player; all percentages use entry count."""
    columns = ["Player", "Overall entries", "Overall %"]
    if special_role:
        columns += [special_role + " entries", special_role + " %", "FLEX entries", "FLEX %"]
    if not isinstance(lineups, pd.DataFrame) or lineups.empty:
        return pd.DataFrame(columns=columns)
    slots = [slot for slot in slots if slot in lineups.columns]
    overall, special, flex = Counter(), Counter(), Counter()
    for _, row in lineups[slots].iterrows():
        names = {slot: str(value).strip() for slot, value in row.items()
                 if pd.notna(value) and str(value).strip()}
        overall.update(set(names.values()))
        if special_role in names:
            special.update([names[special_role]])
        flex.update({name for slot, name in names.items() if slot != special_role})
    count = len(lineups)
    records = []
    for name, appearances in overall.items():
        record = {"Player": name, "Overall entries": appearances,
                  "Overall %": 100 * appearances / count}
        if special_role:
            record.update({special_role + " entries": special[name],
                           special_role + " %": 100 * special[name] / count,
                           "FLEX entries": flex[name], "FLEX %": 100 * flex[name] / count})
        records.append(record)
    return pd.DataFrame(records, columns=columns).sort_values(
        ["Overall entries", "Player"], ascending=[False, True]).reset_index(drop=True)


def exposure_status(lineups, slots, special_role=None, controls=None):
    """Attach saved-limit values and status using the export audit's rules."""
    from simmah_exposure_limits import exposure_violations
    table = player_exposure(lineups, slots, special_role)
    violations = exposure_violations(table, len(lineups), special_role, controls)
    by_player = {}
    for error in violations:
        by_player.setdefault(error["player"], []).append(
            f"❌ {error['role']}: {error['actual']} selected, max {error['limit']}")
    table.insert(1, "Limit status", table["Player"].map(
        lambda name: "; ".join(by_player.get(name, []))))
    controls = controls or {}
    checks = [("Overall Max %", "Max Exposure %")]
    if special_role:
        checks += [(special_role + " Max %", special_role + " Max %"),
                   ("FLEX Max %", "Flex Max %")]
    for label, key in checks:
        def maximum(name):
            config = controls.get(name, {})
            value = pd.to_numeric(config.get(key, 100), errors="coerce")
            if key == "Max Exposure %" and bool(config.get("Fade", False)):
                return 0.
            return float(min(100, max(0, value))) if pd.notna(value) else 100.
        table[label] = table["Player"].map(maximum)
    return table


def render_player_exposure(st, lineups, slots, special_role=None, controls=None):
    table = exposure_status(lineups, slots, special_role, controls)
    st.write("### Your player exposure")
    st.caption(f"Based on {len(lineups):,} assigned entries. Percentages are the share of entries containing each player."
               + (" FLEX combines all non-" + special_role + " slots." if special_role else ""))
    configs = {column: st.column_config.NumberColumn(column, format="%.1f%%")
               for column in table.columns if column.endswith(" %")}
    styled = table.style.map(
        lambda value: "background-color: #53282d; color: #ffb4b4; font-weight: bold" if value else "",
        subset=["Limit status"])
    st.dataframe(styled, hide_index=True, use_container_width=True, column_config=configs)
