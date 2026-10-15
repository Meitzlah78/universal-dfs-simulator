from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel only. DraftKings is intentionally untouched.
# The previous patch referenced fd_build_progress before creating it.
# Create the build progress immediately after the build target is known.
needle = '''            target_lineups = 2000
            max_attempts = 150000 if lineup_mode == "Full Roster" else 500000
            salary_min, salary_max = int(fd_salary_range[0]), min(int(fd_salary_range[1]), 60000)
'''
replacement = '''            target_lineups = 2000
            max_attempts = 150000 if lineup_mode == "Full Roster" else 500000
            salary_min, salary_max = int(fd_salary_range[0]), min(int(fd_salary_range[1]), 60000)
            fd_build_progress = st.progress(
                0,
                text=f"Building FanDuel {lineup_mode} lineups: 0 / {target_lineups:,}"
            )
'''
if needle in text and "fd_build_progress = st.progress" not in text[text.find(needle):text.find(needle)+500]:
    text = text.replace(needle, replacement, 1)

# Make sure the progress object is removed after the build loop.
finish_needle = '''                if len(results) >= target_lineups:
                    break

            if results:
'''
finish_replacement = '''                if len(results) >= target_lineups:
                    break
            fd_build_progress.empty()

            if results:
'''
if finish_needle in text:
    text = text.replace(finish_needle, finish_replacement, 1)

path.write_text(text, encoding="utf-8")
