"""Wire completed-contest field calibration into the deployed Showdown field."""
from pathlib import Path

APP = Path("dfs_app.py")
text = APP.read_text(encoding="utf-8")

anchor = "from zoneinfo import ZoneInfo\n"
new_import = (
    "from dk_showdown_field_calibration import (\n"
    "    calibrated_duplicate_expansion_counts as dk_duplicate_expansion_counts,\n"
    "    projected_duplicate_counts as dk_projected_duplicate_counts,\n"
    ")\n"
)
old_import = (
    "from dk_showdown_field_calibration import (\n"
    "    calibrated_duplicate_expansion_counts as dk_duplicate_expansion_counts,\n"
    ")\n"
)
if new_import not in text:
    if old_import in text:
        text = text.replace(old_import, new_import, 1)
    elif anchor in text:
        text = text.replace(anchor, new_import + anchor, 1)
    else:
        raise SystemExit("zoneinfo import anchor not found")

# The base app already contains ownership-first opponent sampling, historical
# salary acceptance, Captain-role ownership, and opponent-quality filtering.
# Keep the existing calibrated full-field expansion and expose a dedicated
# Projected Dupes estimator from the same field-frequency model. This is additive:
# it does not create a hidden diversification or exposure constraint.
required = (
    "dk_opponent_quality_acceptance",
    "salary_acceptance",
    "expand_showdown_field_by_ownership",
    "dk_duplicate_expansion_counts",
    "dk_projected_duplicate_counts",
)
for marker in required:
    if marker not in text:
        raise SystemExit(f"historical field marker missing: {marker}")

APP.write_text(text, encoding="utf-8")
