from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# Remove the old placeholder from above the build action, if still present.
old_top = '''# Keep the contest-scoring bar in the same visible Build workflow area as SIM/BUILD.\ncontest_progress_slot = st.empty()\n\n# ============================================\n# BUILD ACTION\n# ============================================\n'''
new_top = '''# ============================================\n# BUILD ACTION\n# ============================================\n'''
if old_top in text:
    text = text.replace(old_top, new_top, 1)

# Remove the temporary inside-Step-3 placement from the first version of this patch.
inside_step3 = '''    # Create Step 4 below Step 3 so Streamlit keeps the build workflow in numeric order.\n    contest_progress_slot = st.empty()\n'''
text = text.replace(inside_step3, "", 1)

# Put the placeholder after the full Step 3 block. This keeps Step 4 visually below
# Step 3 and also creates the placeholder on later Streamlit reruns when a saved
# contest field is already present.
anchor = '''\n\n\n# Simulated field ownership is displayed in the Player Pool table, so do not render a duplicate table here.\n'''
replacement = '''\n\n\n# Step 4 belongs directly below the completed Step 3 field-building section.\n# Keep this unconditional so saved builds can be rescored safely on reruns.\ncontest_progress_slot = st.empty()\n\n# Simulated field ownership is displayed in the Player Pool table, so do not render a duplicate table here.\n'''
if "Step 4 belongs directly below the completed Step 3" not in text:
    if anchor not in text:
        raise SystemExit("Could not find Step 3/field ownership anchor")
    text = text.replace(anchor, replacement, 1)

path.write_text(text, encoding="utf-8")
print("Step 4 placement checked.")
