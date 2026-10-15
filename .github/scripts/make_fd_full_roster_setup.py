from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel only. DraftKings is intentionally untouched.
# Add a real visible progress bar to Step 3 so large opponent fields do not look frozen.
needle = '''                with st.spinner(f"Building {fd_opponent_target:,} simulated FanDuel contest entries..."):
                    while len(opponent_rows) < fd_opponent_target and attempts < max(300000, fd_opponent_target * 15):
                        attempts += 1
                        if attempts % 1000 == 0 and fd_opponent_target > 0:
                            max_field_attempts = max(300000, fd_opponent_target * 15)
                            field_progress = max(
                                len(opponent_rows) / max(fd_opponent_target, 1),
                                attempts / max_field_attempts
                            )
                            fd_workflow_status.info(
                                f"Step 3 of 4: Building opponent field — {len(opponent_rows):,} of "
                                f"{fd_opponent_target:,} lineups..."
                            )
'''
replacement = '''                fd_field_progress = st.progress(
                    0,
                    text=f"Building FanDuel opponent field: 0 / {fd_opponent_target:,}"
                )
                with st.spinner(f"Building {fd_opponent_target:,} simulated FanDuel contest entries..."):
                    while len(opponent_rows) < fd_opponent_target and attempts < max(300000, fd_opponent_target * 15):
                        attempts += 1
                        if attempts % 250 == 0 and fd_opponent_target > 0:
                            accepted_progress = len(opponent_rows) / max(fd_opponent_target, 1)
                            fd_field_progress.progress(
                                min(1.0, accepted_progress),
                                text=f"Building FanDuel opponent field: {len(opponent_rows):,} / {fd_opponent_target:,}"
                            )
                            fd_workflow_status.info(
                                f"Step 3 of 4: Building opponent field — {len(opponent_rows):,} of "
                                f"{fd_opponent_target:,} lineups..."
                            )
'''
if needle not in text:
    raise SystemExit("FanDuel opponent-field progress block not found")
text = text.replace(needle, replacement, 1)

needle2 = '''                        opponent_rows.append({**chosen, "Salary": salary, "ProjectedPoints": round(points, 2)})
                opponent_df = pd.DataFrame(opponent_rows)
'''
replacement2 = '''                        opponent_rows.append({**chosen, "Salary": salary, "ProjectedPoints": round(points, 2)})
                        if len(opponent_rows) % 100 == 0 or len(opponent_rows) >= fd_opponent_target:
                            fd_field_progress.progress(
                                min(1.0, len(opponent_rows) / max(fd_opponent_target, 1)),
                                text=f"Building FanDuel opponent field: {len(opponent_rows):,} / {fd_opponent_target:,}"
                            )
                fd_field_progress.empty()
                opponent_df = pd.DataFrame(opponent_rows)
'''
if needle2 not in text:
    raise SystemExit("FanDuel opponent-field append block not found")
text = text.replace(needle2, replacement2, 1)

path.write_text(text, encoding="utf-8")
