from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text()

# This ROI patch has already been applied to the feature app. Keep this script
# safe to rerun so later FanDuel UI patches are not blocked by old markers.
if "# FANDUEL CONTEST ROI: use the same portfolio idea as DraftKings." in s and '"FD Joint Entry"' in s:
    print("FanDuel joint-entry ROI already applied; continuing")
    raise SystemExit(0)

raise SystemExit("FanDuel joint-entry ROI is not present; refusing to overwrite the current ROI implementation")
