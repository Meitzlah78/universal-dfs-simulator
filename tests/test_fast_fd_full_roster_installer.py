from pathlib import Path

APP = Path("dfs_app.py").read_text(encoding="utf-8")
INSTALLER = Path(".github/scripts/install_fast_fd_full_roster_builder.py").read_text(encoding="utf-8")


def test_fd_full_roster_fast_installer_targets_current_hot_loop():
    anchors = [
        'i for i in eligible_indices[slot]',
        'salary + int(salaries[i]) + max_remaining_salary >= salary_min',
        'qb_matches = np.flatnonzero(names == qb_name)',
        'hits = np.flatnonzero(names == str(picked_name))',
        'str(pool.iloc[i].get("Team", "")).strip().upper() == qb_team',
    ]
    for anchor in anchors:
        assert anchor in APP


def test_fd_full_roster_installer_preserves_roster_and_sim_layers():
    assert 'roster = [' not in INSTALLER
    assert 'player_sim' not in INSTALLER
    assert 'Expected ROI (%)' not in INSTALLER
    assert 'opponent_rows' not in INSTALLER


def test_fd_full_roster_installer_adds_vectorized_hot_loop_paths():
    assert 'np.isin(base_choices' in INSTALLER
    assert 'projected_salary = salary + salaries[choices]' in INSTALLER
    assert 'fd_build_name_to_index.get(qb_name)' in INSTALLER
    assert 'fd_build_teams[choices] == qb_team' in INSTALLER
