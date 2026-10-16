"""Temporary runtime launcher for the validated DK Showdown transforms.

This keeps the large legacy app source intact while applying the already-tested
install transforms to a temporary copy before executing Streamlit. It exists so
we can benchmark the real deployed exhaustive build immediately; once the
candidate-build choice is settled, the resulting source can be made permanent.
"""
from pathlib import Path
import os
import runpy
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
LEGACY = ROOT / "dfs_app_legacy.py"
CACHE_DIR = Path(tempfile.gettempdir()) / "simmah_runtime"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
TRANSFORMED = CACHE_DIR / "dfs_app.py"
STAMP = CACHE_DIR / "source_stamp.txt"

source_stamp = f"{LEGACY.stat().st_mtime_ns}:{LEGACY.stat().st_size}"
needs_build = not TRANSFORMED.exists() or not STAMP.exists() or STAMP.read_text() != source_stamp

if needs_build:
    TRANSFORMED.write_bytes(LEGACY.read_bytes())
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    for installer in (
        ROOT / ".github/scripts/install_dk_exhaustive_build.py",
        ROOT / ".github/scripts/install_dk_post_sim_diversification.py",
    ):
        subprocess.run([sys.executable, str(installer)], cwd=str(CACHE_DIR), env=env, check=True)
    compile(TRANSFORMED.read_text(encoding="utf-8"), str(TRANSFORMED), "exec")
    STAMP.write_text(source_stamp)

sys.path.insert(0, str(ROOT))
runpy.run_path(str(TRANSFORMED), run_name="__main__")
