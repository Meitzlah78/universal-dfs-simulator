from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text()
old = "    simulation_values = simulation_df.to_numpy(dtype=np.float32, copy=False)\n    batch_size = 128\n"
new = "    simulation_values = simulation_df.to_numpy(dtype=np.float32, copy=False)\n    # Production-shaped benchmark: 64-scenario batches were fastest with the\n    # existing four-worker DK Showdown scoring path. Scheduling only; scoring\n    # and rank semantics are unchanged.\n    batch_size = 64 if is_dk_showdown else 128\n"
if text.count(old) != 1:
    raise SystemExit(f"expected exactly one scoring batch anchor, found {text.count(old)}")
path.write_text(text.replace(old, new, 1))
