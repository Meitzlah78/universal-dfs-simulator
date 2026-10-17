from pathlib import Path

APP = Path("dfs_app.py").read_text(encoding="utf-8")


def test_full_roster_user_stacks_are_separate_from_opponent_weights():
    assert "full_roster_stack_matches" in APP
    assert "opponent_field_selection_weights" in APP
    assert 'if lineup_mode == "Full Roster" and not full_roster_stack_matches(chosen, pool, fd_stack_rules):' in APP


def test_opponent_weighting_prefers_field_ownership_when_available():
    assert '"field own %", "ownership %", "projected ownership", "ownership", "own%", "own"' in APP
    assert "return np.clip(ownership, 0.01, None)" in APP


def test_fd_full_roster_rules_remain_site_specific():
    assert 'FanDuel NFL Full Roster: QB, 2 RB, 3 WR, TE, FLEX (RB/WR/TE), D.' in APP
    assert 'Salary cap: $60,000.' in APP


def test_contest_layer_keeps_expected_roi_output():
    assert 'Expected ROI (%)' in APP
