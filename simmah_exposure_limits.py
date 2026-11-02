"""Hard portfolio ceilings shared by selection and exact entry exports."""
import math
import pandas as pd
from simmah_player_exposure import player_exposure


def validate_exposure_limits(portfolio, slots, controls=None):
    """Raise with player/role/count details; never relax a manual ceiling."""
    controls = controls or {}
    special = next((s for s in slots if s in ("Captain", "MVP")), None)
    table = player_exposure(portfolio, slots, special)
    count = len(portfolio)
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
                errors.append(f"{name}: {label} {actual}/{count} exceeds {value:g}% (max {limit})")
    if errors:
        raise ValueError("Exposure limits exceeded — " + "; ".join(errors))
    return table
