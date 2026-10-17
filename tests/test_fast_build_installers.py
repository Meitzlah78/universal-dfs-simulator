from pathlib import Path

ROOT = Path(".github/scripts")

INSTALLERS = {
    "dk_classic": ROOT / "install_fast_classic_builder.py",
    "fd_single_game": ROOT / "install_fast_fd_single_game_builder.py",
    "fd_full_roster": ROOT / "install_fast_fd_full_roster_builder.py",
    "fd_setup": ROOT / "install_fast_fd_build_setup.py",
    "stack_validation": ROOT / "install_fast_stack_validation.py",
}


def _text(name):
    path = INSTALLERS[name]
    assert path.exists(), f"Missing installer: {path}"
    return path.read_text(encoding="utf-8")


def test_all_fast_builder_installers_leave_simulation_and_roi_layers_alone():
    forbidden = ["Expected ROI (%)", "opponent_rows", "player_sim = {}"]
    for name in INSTALLERS:
        text = _text(name)
        for token in forbidden:
            assert token not in text, f"{name} unexpectedly touches {token}"


def test_fd_fast_paths_preserve_site_roster_rules():
    single = _text("fd_single_game")
    full = _text("fd_full_roster")
    setup = _text("fd_setup")
    assert 'mvp_idx = int(rng.choice' not in single
    assert 'roster = [' not in full
    assert 'salary_max' in single
    assert 'salary_max' in full
    assert 'lineup_mode == "Full Roster"' in setup


def test_fast_paths_use_precomputed_or_vectorized_filters():
    classic = _text("dk_classic")
    single = _text("fd_single_game")
    full = _text("fd_full_roster")
    setup = _text("fd_setup")
    stack = _text("stack_validation")
    assert "np.asarray" in classic or "np.isin" in classic
    assert "np.isin(fd_all_player_indices" in single
    assert "np.isin(base_choices" in full
    assert "fd_build_name_to_index" in setup
    assert "stack_lookup=None" in stack
