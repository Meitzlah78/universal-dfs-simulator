from pathlib import Path

APP = Path("dfs_app.py").read_text(encoding="utf-8")
INSTALLER = Path(".github/scripts/install_fast_fd_single_game_builder.py").read_text(encoding="utf-8")


def test_fd_single_game_current_flex_hot_loop_anchor_exists():
    assert 'i for i in range(len(names))' in APP
    assert 'if i not in used and salary + salaries[i] <= salary_max' in APP


def test_fd_single_game_installer_vectorizes_flex_choices_only():
    assert 'fd_all_player_indices = np.arange(len(names), dtype=int)' in INSTALLER
    assert 'np.isin(fd_all_player_indices' in INSTALLER
    assert 'salary + salaries[fd_all_player_indices] <= salary_max' in INSTALLER


def test_fd_single_game_installer_preserves_mvp_and_contest_layers():
    assert 'mvp_idx = int(rng.choice' not in INSTALLER
    assert 'mvp_weights' not in INSTALLER
    assert 'player_sim' not in INSTALLER
    assert 'opponent_rows' not in INSTALLER
    assert 'Expected ROI (%)' not in INSTALLER
