from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text()

old = '''            if scoring_multiplier == 1.5 and _diag_candidate_idx.shape[1] == 6:
                _diag_scores = dk_score_lineup_matrix(
                    _diag_values, _diag_candidate_idx[:, 0], _diag_candidate_idx[:, 1:]
                )
                _diag_field_scores = dk_score_lineup_matrix(
                    _diag_values, contest_idx[:, 0], contest_idx[:, 1:]
                )
            else:
                _diag_scores = _diag_values[:, _diag_candidate_idx].sum(axis=2)
                _diag_field_scores = _diag_values[:, contest_idx].sum(axis=2)
            _diag_sorted = np.sort(_diag_field_scores, axis=1)
            _diag_greater = np.empty_like(_diag_scores, dtype=np.float64)
            for _r in range(_diag_scores.shape[0]):
                _diag_greater[_r] = total_field - np.searchsorted(_diag_sorted[_r], _diag_scores[_r], side="right")
            _diag_percentiles = 1.0 - (_diag_greater / max(1, total_field))
'''
new = '''            if is_dk_showdown:
                _diag_scores = dk_score_lineup_matrix(
                    _diag_values, _diag_candidate_idx[:, 0], _diag_candidate_idx[:, 1:]
                )
                _diag_field_scores = dk_score_lineup_matrix(
                    _diag_values, contest_unique_idx[:, 0], contest_unique_idx[:, 1:]
                )
                _, _diag_right = dk_weighted_score_bounds(
                    _diag_field_scores, contest_multiplicity, _diag_scores
                )
                _diag_greater = total_field - _diag_right
            else:
                _diag_scores = _diag_values[:, _diag_candidate_idx].sum(axis=2)
                _diag_field_scores = _diag_values[:, contest_idx].sum(axis=2)
                if scoring_multiplier != 1.0:
                    _diag_scores += _diag_values[:, _diag_candidate_idx[:, 0]] * (scoring_multiplier - 1.0)
                    _diag_field_scores += _diag_values[:, contest_idx[:, 0]] * (scoring_multiplier - 1.0)
                _diag_sorted = np.sort(_diag_field_scores, axis=1)
                _diag_greater = total_field - np.sum(
                    _diag_sorted[:, :, None] <= _diag_scores[:, None, :], axis=1
                )
            _diag_percentiles = 1.0 - (_diag_greater / max(1, total_field))
'''
if old not in text:
    raise SystemExit("holdout diagnostic target not found")
text = text.replace(old, new, 1)

old_sanity = '''        _rng=np.random.default_rng(20261014); _idx=contest_idx[_rng.choice(total_field,_sanity_n,replace=False)]; _counts=np.zeros(4); _obs=0
        for _start in range(0,selection_n_sims,batch_size):
            _end=min(_start+batch_size,selection_n_sims); _v=simulation_values[_start:_end]; _s=_v[:,_idx].sum(axis=2); _f=_v[:,contest_idx].sum(axis=2)
            if scoring_multiplier != 1.0:
                _s += _v[:,_idx[:,0]]*(scoring_multiplier-1.0); _f += _v[:,contest_idx[:,0]]*(scoring_multiplier-1.0)
            _sorted=np.sort(_f,axis=1); _greater=total_field-np.sum(_sorted[:,:,None] <= _s[:,None,:],axis=1); _pct=1.0-_greater/max(1,total_field)
'''
new_sanity = '''        _rng=np.random.default_rng(20261014); _idx=contest_idx[_rng.choice(total_field,_sanity_n,replace=False)]; _counts=np.zeros(4); _obs=0
        for _start in range(0,selection_n_sims,batch_size):
            _end=min(_start+batch_size,selection_n_sims); _v=simulation_values[_start:_end]
            if is_dk_showdown:
                _s=dk_score_lineup_matrix(_v,_idx[:,0],_idx[:,1:]); _f=dk_score_lineup_matrix(_v,contest_unique_idx[:,0],contest_unique_idx[:,1:])
                _,_right=dk_weighted_score_bounds(_f,contest_multiplicity,_s); _greater=total_field-_right
            else:
                _s=_v[:,_idx].sum(axis=2); _f=_v[:,contest_idx].sum(axis=2)
                if scoring_multiplier != 1.0:
                    _s += _v[:,_idx[:,0]]*(scoring_multiplier-1.0); _f += _v[:,contest_idx[:,0]]*(scoring_multiplier-1.0)
                _sorted=np.sort(_f,axis=1); _greater=total_field-np.sum(_sorted[:,:,None] <= _s[:,None,:],axis=1)
            _pct=1.0-_greater/max(1,total_field)
'''
if old_sanity not in text:
    raise SystemExit("field sanity target not found")
text = text.replace(old_sanity, new_sanity, 1)

path.write_text(text)
print("wired DK compressed diagnostic hotpaths")
