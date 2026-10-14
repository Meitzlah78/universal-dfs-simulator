from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text(encoding='utf-8')
old = '''        with build_cols[2]:
            st.write("### Run")
            _classic_run_cols = st.columns(3)
            with _classic_run_cols[0]:
                _classic_sim_button = st.button("SIM", type="primary", use_container_width=True, key="dk_classic_sim")
            with _classic_run_cols[1]:
                _classic_build_button = st.button("BUILD", use_container_width=True, key="dk_classic_build")
            with _classic_run_cols[2]:
                _classic_contest_button = st.button("CONTEST SIM", use_container_width=True, key="dk_classic_contest")
            classic_run_all = _classic_sim_button or _classic_build_button or _classic_contest_button
'''
new = '''        with build_cols[2]:
            st.write("### Run")
            _classic_sim_button = st.button(
                "SIM", type="primary", use_container_width=True, key="dk_classic_sim"
            )
            # One-click Classic workflow: SIM -> BUILD -> CONTEST SIM -> ROI.
            _classic_build_button = _classic_sim_button
            _classic_contest_button = _classic_sim_button
            classic_run_all = _classic_sim_button
'''
if old not in text:
    raise SystemExit('Classic three-button block not found')
text = text.replace(old, new, 1)
path.write_text(text, encoding='utf-8')
print('Classic now uses one SIM button for the full workflow.')
