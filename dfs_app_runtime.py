"""Runtime entry point for the validated DK Showdown transforms.

The large legacy app is loaded from the repository's pinned pre-launch commit,
then the already-tested install transforms are applied to a cached temporary
copy before Streamlit executes it. This avoids duplicating the large app file
while keeping the deployed source deterministic.
"""
from pathlib import Path
import os
import runpy
import subprocess
import sys
import tempfile
import requests

ROOT = Path(__file__).resolve().parent
CACHE_DIR = Path(tempfile.gettempdir()) / "simmah_runtime"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
TRANSFORMED = CACHE_DIR / "dfs_app.py"
STAMP = CACHE_DIR / "source_stamp.txt"
SOURCE_COMMIT = "40f00bce67aff5772b25971d4f2f8153aba386da"
SOURCE_URL = f"https://raw.githubusercontent.com/Meitzlah78/universal-dfs-simulator/{SOURCE_COMMIT}/dfs_app.py"
source_stamp = SOURCE_COMMIT
needs_build = not TRANSFORMED.exists() or not STAMP.exists() or STAMP.read_text() != source_stamp

if needs_build:
    response = requests.get(SOURCE_URL, timeout=30)
    response.raise_for_status()
    TRANSFORMED.write_bytes(response.content)
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
