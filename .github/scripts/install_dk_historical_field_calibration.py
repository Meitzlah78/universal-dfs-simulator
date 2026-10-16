"""Wire completed-contest field calibration into the deployed Showdown field."""
from pathlib import Path

APP = Path("dfs_app.py")
text = APP.read_text(encoding="utf-8")

anchor = "from zoneinfo import ZoneInfo\n"
new_import = (
    "from dk_showdown_field_calibration import (\n"
    "    calibrated_duplicate_expansion_counts as dk_duplicate_expansion_counts,\n"
    ")\n"
)
if new_import not in text:
    if anchor not in text:
        raise SystemExit("zoneinfo import anchor not found")
    text = text.replace(anchor, new_import + anchor, 1)

# The base app already contains ownership-first opponent sampling, historical
# salary acceptance, Captain-role ownership, and opponent-quality filtering.
# This override fixes the remaining failure seen in the SEA/DEN export: full-
# field duplicate expansion collapsing 47k entries into only ~4k constructions
# with a single lineup receiving thousands of copies.
required = (
    "dk_opponent_quality_acceptance",
    "salary_acceptance",
    "expand_showdown_field_by_ownership",
    "dk_duplicate_expansion_counts",
)
for marker in required:
    if marker not in text:
        raise SystemExit(f"historical field marker missing: {marker}")

APP.write_text(text, encoding="utf-8")
