from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

old_top = '''# Keep the contest-scoring bar in the same visible Build workflow area as SIM/BUILD.\ncontest_progress_slot = st.empty()\n\n# ============================================\n# BUILD ACTION\n# ============================================\n'''
new_top = '''# ============================================\n# BUILD ACTION\n# ============================================\n'''

if old_top in text:
    text = text.replace(old_top, new_top, 1)

old_step3 = '''    workflow_status.info(f"Step 3 of 4: Building up to {dk_opponent_target:,} simulated opponent lineups...")\n    field_progress = st.progress(0, text=f"Step 3 of 4: Building opponent lineups (0 of {dk_opponent_target:,})...")\n'''
new_step3 = '''    workflow_status.info(f"Step 3 of 4: Building up to {dk_opponent_target:,} simulated opponent lineups...")\n    field_progress = st.progress(0, text=f"Step 3 of 4: Building opponent lineups (0 of {dk_opponent_target:,})...")\n    # Create Step 4 below Step 3 so Streamlit keeps the build workflow in numeric order.\n    contest_progress_slot = st.empty()\n'''

if old_step3 in text and "Create Step 4 below Step 3" not in text:
    text = text.replace(old_step3, new_step3, 1)

path.write_text(text, encoding="utf-8")
print("Step 4 placement checked.")
