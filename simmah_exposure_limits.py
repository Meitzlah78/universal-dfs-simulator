"""Hard portfolio ceilings shared by selection and exact entry exports."""
import math
import pandas as pd
from simmah_player_exposure import player_exposure


def exposure_violations(table, count, special=None, controls=None):
    """Structured violations used by both the visible status and export gate."""
    controls = controls or {}
    errors = []
    for _, row in table.iterrows():
        name = row["Player"]
        config = controls.get(name, {})
        checks = [("Overall", "Max Exposure %", "Overall entries")]
        if special:
            checks += [(special, special + " Max %", special + " entries"),
                       ("FLEX", "Flex Max %", "FLEX entries")]
        for label, key, column in checks:
            value = pd.to_numeric(config.get(key, 100), errors="coerce")
            value = float(min(100, max(0, value))) if pd.notna(value) else 100.
            if label == "Overall" and bool(config.get("Fade", False)):
                value = 0.
            limit = math.floor(count * value / 100 + 1e-9)
            actual = int(row[column])
            if actual > limit:
                errors.append({"player": name, "role": label, "actual": actual,
                               "count": count, "percent": value, "limit": limit})
    return errors


def validate_exposure_limits(portfolio, slots, controls=None):
    """Raise with player/role/count details; never relax a manual ceiling."""
    special = next((s for s in slots if s in ("Captain", "MVP")), None)
    table = player_exposure(portfolio, slots, special)
    errors = exposure_violations(table, len(portfolio), special, controls)
    if errors:
        messages = [f"{e['player']}: {e['role']} {e['actual']}/{e['count']} exceeds "
                    f"{e['percent']:g}% (max {e['limit']})" for e in errors]
        raise ValueError("Exposure limits exceeded — " + "; ".join(messages))
    return table
