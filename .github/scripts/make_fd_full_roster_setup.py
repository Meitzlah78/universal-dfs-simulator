from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel Full Roster only. DraftKings is intentionally untouched.
# Match DK Classic's candidate-build count and progress-bar behavior.
needle = '''            target_lineups = 2000
            max_attempts = 150000 if lineup_mode == "Full Roster" else 500000
'''
replacement = '''            target_lineups = 5000 if lineup_mode == "Full Roster" else 2000
            max_attempts = 30000 if (lineup_mode == "Full Roster" and ((not fd_stack_rules) or ("No stack rule" in fd_stack_rules))) else (100000 if lineup_mode == "Full Roster" else 500000)
'''
if needle not in text:
    raise SystemExit("FanDuel target/progress setup not found")
text = text.replace(needle, replacement, 1)

needle2 = '''            for build_attempt in range(max_attempts):
                if build_attempt % 250 == 0:
                    fd_build_progress.progress(
                        min(0.99, build_attempt / max_attempts),
                        text=f"Building FanDuel {lineup_mode} lineups: {len(results):,} / {target_lineups:,} (checking valid rosters)"
                    )
'''
replacement2 = '''            for build_attempt in range(max_attempts):
                if build_attempt % 250 == 0 and len(results) == 0:
                    fd_build_progress.progress(
                        min(0.99, build_attempt / max_attempts),
                        text=f"Building FanDuel {lineup_mode} lineups: {len(results):,} / {target_lineups:,} (checking valid rosters)"
                    )
'''
if needle2 not in text:
    raise SystemExit("FanDuel build progress loop not found")
text = text.replace(needle2, replacement2, 1)

path.write_text(text, encoding="utf-8")
