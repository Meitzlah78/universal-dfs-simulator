from pathlib import Path


def test_candidate_batch_patch_has_safety_anchor_and_bounded_batches():
    text = Path('.github/scripts/wire_dk_candidate_batch_sampler.py').read_text()
    assert "SAFE_ABORT candidate loop anchor" in text
    assert "batch_n = min(" in text
    assert "512" in text
    assert "np.argpartition" in text
    assert "rng.gumbel" in text


def test_candidate_batch_patch_preserves_existing_validation_body():
    text = Path('.github/scripts/wire_dk_candidate_batch_sampler.py').read_text()
    assert "flex_key = tuple(sorted(flex_players))" in text
    assert "candidates.extend(captain_candidates)" in text
