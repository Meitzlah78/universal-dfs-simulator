from pathlib import Path
import subprocess
import sys


def test_unique_field_patch_inserts_dk_only_compression(tmp_path):
    source = Path("dfs_app.py").read_text()
    target = tmp_path / "dfs_app.py"
    target.write_text(source)
    script = Path(".github/scripts/wire_dk_unique_field_indices.py").read_text()
    patch = tmp_path / "patch.py"
    patch.write_text(script)
    subprocess.run([sys.executable, str(patch)], cwd=tmp_path, check=True)
    transformed = target.read_text()
    assert 'is_dk_showdown = platform == "DraftKings" and lineup_mode != "Classic"' in transformed
    assert 'np.unique(\n            _contest_canonical, axis=0, return_counts=True' in transformed
    assert 'contest_multiplicity = np.ones(len(contest_idx), dtype=np.int32)' in transformed
    compile(transformed, "dfs_app.py", "exec")
