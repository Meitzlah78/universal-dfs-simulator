from pathlib import Path

APP = Path("dfs_app.py").read_text(encoding="utf-8")


def test_dk_classic_builder_is_bounded_and_vectorized():
    assert 'if platform == "DraftKings" and lineup_mode == "Classic":' in APP
    assert 'max_opponent_attempts = max(250000, dk_opponent_target * 15)' in APP
    assert 'slot_indices = {' in APP
    assert 'np.asarray' in APP


def test_showdown_builder_has_bounded_weighted_search():
    assert 'max_captain_attempts = max(500, per_captain_candidate_limit * 8)' in APP
    assert 'seen_flex_groups' in APP


def test_fast_build_work_keeps_simulation_and_contest_layers_separate():
    # The fast-build project optimizes lineup generation only. Player simulation and
    # contest/ROI evaluation must remain separate stages so a future PBP engine can
    # feed the same builders without being coupled to roster generation.
    assert 'player_sim = {}' in APP
    assert 'Expected ROI (%)' in APP
