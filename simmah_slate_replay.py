"""Offline NFL single-game replay. Never refit or use actual scores for selection.

Random baselines are uniformly drawn unique portfolios, rejection conditioned on
the frozen selector's exposure limits. This is a development diagnostic, not an
untouched out-of-sample experiment or a population-level claim of predictive edge.
"""
from collections import Counter
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

import numpy as np
import pandas as pd

from simmah_contest_history import TOKEN, name_key
from simmah_portfolio_selection import select_portfolio
from simmah_slate_workspaces import decode


def canonical(names):
    names = tuple(name_key(n) for n in names)
    if len(names) != 6 or len(set(names)) != 6 or not all(names):
        raise ValueError('A single-game roster must have six different players')
    return names[0], tuple(sorted(names[1:]))


def parse_roster(raw):
    return canonical([n.strip(' ,;|') for _, n in TOKEN.findall(str(raw))])


def payout_schedule(tiers, count, prize_pool):
    """Validate non-overlapping tiers, nonnegative finite payouts, and prize mass."""
    payouts = np.zeros(count, float)
    covered = np.zeros(count, bool)
    for lo, hi, amount in tiers:
        if (type(lo) is not int or type(hi) is not int or not 1 <= lo <= hi <= count
                or not np.isfinite(amount) or amount < 0 or covered[lo-1:hi].any()):
            raise ValueError('Invalid or overlapping payout tiers')
        covered[lo-1:hi] = True
        payouts[lo-1:hi] = amount
    if not np.isclose(payouts.sum(), prize_pool, atol=.005, rtol=0):
        raise ValueError('Payout schedule does not reconcile to prize pool')
    return payouts


def replacement_prizes(portfolios, opponent_scores, payouts):
    """Insert complete portfolios into the fixed opponent field; split every tie.

    Scores are integer hundredths of NFL fantasy points. Opponents include all
    official entries, even entries whose roster text is empty or unparseable.
    This preserves contest size and rank mass without inventing opponent rows.
    """
    scores = np.atleast_2d(np.asarray(portfolios, np.int64))
    opponents = np.sort(np.asarray(opponent_scores, np.int64))
    if len(payouts) != len(opponents) + scores.shape[1]:
        raise ValueError('Opponent count plus portfolio must equal contest size')
    prefix = np.r_[0., np.cumsum(payouts)]
    better = len(opponents) - np.searchsorted(opponents, scores, side='right')
    tied = (np.searchsorted(opponents, scores, side='right')
            - np.searchsorted(opponents, scores, side='left'))
    better += (scores[:, :, None] < scores[:, None, :]).sum(axis=2)
    tied += (scores[:, :, None] == scores[:, None, :]).sum(axis=2)
    return (prefix[better+tied] - prefix[better]) / tied


def exposure_matrix(rosters, player_names):
    lookup = {n: i for i, n in enumerate(player_names)}
    incidence = np.zeros((len(rosters), 2*len(player_names)), np.int16)
    for i, (special, flex) in enumerate(rosters):
        for n in (special, *flex):
            incidence[i, lookup[n]] = 1
        incidence[i, len(player_names)+lookup[special]] = 1
    return incidence


def exposure_limits(names, controls, count, auto_cap, special):
    """Mirror overall and role limits without inferring limits from realized picks."""
    lower, upper, role_lower, role_upper = [], [], [], []
    for name in names:
        cfg = controls.get(name, {})
        minimum = float(cfg.get('Min Exposure %', 0))
        maximum = float(cfg.get('Max Exposure %', 100))
        if cfg.get('Lock', False):
            minimum = 100.
        elif minimum <= auto_cap:
            maximum = min(maximum, auto_cap)
        if cfg.get('Fade', False):
            maximum = 0.
        lower.append(int(np.ceil(count*minimum/100-1e-9)))
        upper.append(0 if maximum <= 0 else max(1, int(np.floor(count*maximum/100+1e-9))))
        role_lower.append(int(np.ceil(count*float(cfg.get(special+' Min %', 0))/100-1e-9)))
        role_upper.append(int(np.floor(count*float(cfg.get(special+' Max %', 100))/100+1e-9)))
    return np.r_[lower, role_lower], np.r_[upper, role_upper]


def random_portfolios(size, count, incidence, lower, upper, draws=10000, seed=83):
    """Rejection sampling preserves the uniform constrained subset distribution."""
    if not 0 < count <= size or draws < 1:
        raise ValueError('Invalid portfolio sample size')
    rng = np.random.default_rng(seed)
    accepted, attempted = [], 0
    while len(accepted) < draws and attempted < draws*100:
        picks = rng.choice(size, size=count, replace=False)
        attempted += 1
        counts = incidence[picks].sum(axis=0)
        if (counts >= lower).all() and (counts <= upper).all():
            accepted.append(picks)
    if len(accepted) != draws:
        raise ValueError('Insufficient constrained random samples; no constraints were relaxed')
    return np.asarray(accepted), attempted


def _standings(path):
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            files = [n for n in archive.namelist() if n.lower().endswith('.csv')]
            if len(files) != 1:
                raise ValueError('Expected one standings CSV')
            return pd.read_csv(io.BytesIO(archive.read(files[0])), low_memory=False)
    return pd.read_csv(path, low_memory=False)


def official_scores(standings):
    values = pd.to_numeric(standings.Points).to_numpy(float)
    missing = np.isnan(values)
    if np.isinf(values).any():
        raise ValueError('Invalid infinite entry score')
    if missing.any():
        # FD lists unfilled entries with no score/roster, tied behind all scored
        # entries. Retain these rows as bottom-ranked entries, not zero-pointers.
        if (standings.loc[missing,'Lineup'].notna().any()
                or not standings.loc[missing,'Rank'].eq(int((~missing).sum())+1).all()):
            raise ValueError('Missing score is not a verified empty bottom-ranked entry')
    result = np.full(len(values), -(2**62), np.int64)
    result[~missing] = np.rint(values[~missing]*100).astype(np.int64)
    return result


def published_player_scores(standings, dk):
    result = {}
    for row in standings.dropna(subset=['Player','FPTS']).to_dict('records'):
        k, points = name_key(row['Player']), float(row['FPTS'])
        if dk and str(row['Roster Position']).upper() in ('CPT','CAPTAIN'):
            points /= 1.5
        if not np.isfinite(points) or (k in result and not np.isclose(result[k],points)):
            raise ValueError('Conflicting or invalid player scores')
        result[k] = points
    return result


def field_summary(rosters):
    counts = Counter(rosters)
    ownership = Counter(n for special, flex in rosters for n in (special,*flex))
    return dict(valid_entries=len(rosters), distinct_lineups=len(counts),
        most_common_lineup_copies=max(counts.values(),default=0),
        most_common_lineup_fraction=max(counts.values(),default=0)/max(1,len(rosters)),
        ownership_pct={n:100*c/max(1,len(rosters)) for n,c in ownership.items()})


def replay(package_path, standings_path, username, lock_time, *, draws=10000, seed=83):
    lock = datetime.fromisoformat(lock_time)
    if lock.tzinfo is None:
        raise ValueError('Explicit timezone-aware lock time required')
    with zipfile.ZipFile(package_path) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        for name, expected in manifest['files'].items():
            raw = archive.read(name)
            if len(raw) != expected['bytes'] or hashlib.sha256(raw).hexdigest() != expected['sha256']:
                raise ValueError('Package integrity failed: '+name)
        capture = datetime.fromisoformat(manifest['captured_at_utc'])
        if capture >= lock:
            raise ValueError('Package capture is not before the supplied lock time')
        # Do not execute arbitrary archived Python. Require the reviewed local
        # selector to match the archived bytes exactly before invoking it.
        selector = Path(__file__).with_name('simmah_portfolio_selection.py').read_bytes()
        if selector != archive.read('implementation/simmah_portfolio_selection.py'):
            raise ValueError('Local selector differs from frozen package implementation')
        contest = json.loads(archive.read('inputs/contest.json'))
        state = dict(json.loads(archive.read('solver/runtime_state.json'))['value'])
        pool = pd.read_csv(archive.open('player_pool.csv'))
        candidates = pd.read_csv(archive.open('scored_lineups.csv'))
        raw_candidates = pd.read_csv(archive.open('candidates.csv'))
        field = pd.read_csv(archive.open('opponent_field.csv'))
        with np.load(io.BytesIO(archive.read('solver/evaluation_outcomes.npz')), allow_pickle=False) as arrays:
            outcome_shape = list(arrays['values'].shape)
            if outcome_shape[1] != len(arrays['names']) or not np.isfinite(arrays['values']).all():
                raise ValueError('Invalid frozen evaluation arrays')
    dk = manifest['format'] == 'DraftKings Showdown'
    if not dk and manifest['format'] != 'FanDuel Single Game':
        raise ValueError('This replay supports NFL Showdown and Single Game only')
    slots = ['Captain','Flex1','Flex2','Flex3','Flex4','Flex5'] if dk else ['MVP','FLEX1','FLEX2','FLEX3','FLEX4','FLEX5']
    controls_key = 'control_values' if dk else 'fd_player_controls_Single Game'
    controls = decode(state[controls_key]).set_index('Name').to_dict('index')
    stack_prefix = 'single_stacks_DraftKings_Showdown_' if dk else 'single_stacks_FanDuel_Single Game_'
    splits = decode(state.get(stack_prefix+'splits',[]))
    if state.get(stack_prefix+'qb_receiver') or (splits and splits != ['Any / All']):
        raise ValueError('Active stacking controls need an explicit replay validator')
    diversity = state['portfolio_exposure_diversity_DraftKings_Showdown_v1' if dk else 'portfolio_exposure_diversity_FanDuel_Single Game_v1']
    metric = state['portfolio_metric_used'] if dk else 'Top1'
    count = int(contest['your_entries'])
    # Selection occurs before standings are loaded. No postgame quantities enter
    # this call or determine diversity, constraints, metric, seed or sample count.
    selected = select_portfolio(candidates, slots, count, metric, controls=controls, diversity=diversity)
    roster_keys = [canonical(row) for row in candidates[slots].itertuples(index=False, name=None)]
    raw_keys = [canonical(row) for row in raw_candidates[slots].itertuples(index=False, name=None)]
    if Counter(raw_keys) != Counter(roster_keys):
        raise ValueError('Scored candidate universe differs from frozen build')
    duplicate_candidates = len(roster_keys)-len(set(roster_keys))
    keep = ~pd.Series(roster_keys).duplicated().to_numpy()
    candidates = candidates.loc[keep].reset_index(drop=True)
    roster_keys = [k for k, valid in zip(roster_keys, keep) if valid]
    selected_keys = [canonical(row) for row in selected[slots].itertuples(index=False, name=None)]
    lookup = {k:i for i,k in enumerate(roster_keys)}
    selected_indices = np.array([lookup[k] for k in selected_keys])
    names = sorted({n for special, flex in roster_keys for n in (special, *flex)})
    normalized_controls = {name_key(k):v for k,v in controls.items()}
    incidence = exposure_matrix(roster_keys, names)
    lower, upper = exposure_limits(names, normalized_controls, count,
        selected.attrs['effective_auto_cap_pct'], 'Captain' if dk else 'MVP')
    selected_counts = incidence[selected_indices].sum(axis=0)
    if (selected_counts < lower).any() or (selected_counts > upper).any():
        raise ValueError('Frozen selection violates replay exposure bounds')
    random_indices, attempts = random_portfolios(len(roster_keys), count, incidence, lower, upper, draws, seed)
    standings = _standings(standings_path)
    if standings.EntryId.isna().any() or standings.EntryId.duplicated().any():
        raise ValueError('Missing or repeated entry IDs; repeated lineups are allowed')
    if 'TimeRemaining' in standings and not pd.to_numeric(standings.TimeRemaining).eq(0).all():
        raise ValueError('Contest is not final')
    actual_scores = official_scores(standings)
    sorted_scores = np.sort(actual_scores)
    expected_ranks = 1+len(sorted_scores)-np.searchsorted(sorted_scores, actual_scores, side='right')
    if not np.array_equal(expected_ranks, standings.Rank.to_numpy(int)):
        raise ValueError('Published ranks disagree with entry score counts')
    mine = standings.EntryName.fillna('').str.match('(?i)^'+re.escape(username)+r'(?:\s|$)').to_numpy()
    if mine.sum() != count:
        raise ValueError('Entered portfolio count differs from frozen contest settings')
    payouts = payout_schedule(contest['payouts'], len(standings), contest['prize_pool'])
    player_scores = published_player_scores(standings,dk)
    def actual_points(k):
        captain, flex = k
        return int(round(100*(1.5*player_scores[captain]+sum(player_scores[p] for p in flex))))
    parsed, unavailable = [], 0
    for raw, points in zip(standings.Lineup, actual_scores):
        try:
            k = parse_roster(raw)
        except ValueError:
            parsed.append(None); unavailable += 1; continue
        if actual_points(k) != points:
            raise ValueError('Roster points do not reconcile; special-role order is unverified')
        parsed.append(k)
    entered = [k for k, yes in zip(parsed, mine) if yes]
    if any(k not in lookup for k in entered):
        raise ValueError('Some entered lineups are absent from frozen candidates')
    # Legality uses the captured salary file and site-specific special-role salary.
    metadata = {name_key(row['Name']):row for row in pool.to_dict('records')}
    salary_min = (state['dk_build_salary_range_draftkings_showdown'] if dk else state['fd_build_salary_range_single_game'])['value'][0]
    cap = 50000 if dk else 60000
    for special, flex in roster_keys:
        special_salary = metadata[special].get('CaptainSalary',1.5*metadata[special]['Salary']) if dk else 1.5*metadata[special]['Salary']
        salary = special_salary+sum(metadata[p]['Salary'] for p in flex)
        if not salary_min <= salary <= cap or len({metadata[p]['Team'] for p in (special,*flex)}) != 2:
            raise ValueError('Candidate violates captured salary or both-teams constraints')
    scores = np.array([actual_points(k) for k in roster_keys])
    opponents = actual_scores[~mine]
    fee = float(contest['entry_fee'])
    if not np.isfinite(fee) or fee <= 0:
        raise ValueError('Positive entry fee required for ROI')
    fees = count*fee
    def evaluate(indices):
        return replacement_prizes(scores[indices], opponents, payouts).sum(axis=1)
    random_winnings = np.concatenate([evaluate(random_indices[i:i+256]) for i in range(0,draws,256)])
    replay_winnings = float(evaluate(selected_indices)[0])
    entered_indices = np.array([lookup[k] for k in entered])
    entered_winnings = float(evaluate(entered_indices)[0])
    official_prizes = replacement_prizes(actual_scores[mine], opponents, payouts)[0]
    if not np.isclose(official_prizes.sum(), entered_winnings, atol=1e-8):
        raise ValueError('Entered payout replay failed reconciliation')
    random_roi = 100*(random_winnings/fees-1)
    replay_roi = 100*(replay_winnings/fees-1)
    entered_roi = 100*(entered_winnings/fees-1)
    actual_field = field_summary([k for k, yes in zip(parsed,mine) if not yes and k is not None])
    simulated_field = field_summary([canonical(row) for row in field[slots].itertuples(index=False,name=None)])
    histogram_edges = np.arange(-100.,105.,5.)
    if random_roi.max() > 100:
        histogram_edges = np.r_[histogram_edges,random_roi.max()+1.]
    histogram_counts, histogram_edges = np.histogram(random_roi,bins=histogram_edges)
    warnings = ['Development replay: this game was already inspected; not untouched out-of-sample evidence.',
        'DK and FD on the same game are correlated, not independent slates.',
        'Saved payout schedule is not independently verified against a final site payout receipt.',
        'No exact export checkpoint is present; entered rosters are recovered from standings.',
        'No production IndexedDB restore or CSV replacement upload is exercised by this offline replay.']
    if not dk:
        warnings += ['FD ranking metric defaults to Top1 because the widget value was not captured.',
            'FD standings contain no TimeRemaining column; final status is not machine-verifiable from this file.',
            'FD saved payout profile is labeled Thursday for a Monday contest; treat monetary results as provisional.']
    return dict(schema=1, contest_id=manifest['contest_id'], platform=manifest['platform'],
        package_sha256=hashlib.sha256(Path(package_path).read_bytes()).hexdigest(),
        standings_sha256=hashlib.sha256(Path(standings_path).read_bytes()).hexdigest(),
        selector_sha256=hashlib.sha256(selector).hexdigest(), captured_at=manifest['captured_at_utc'],
        supplied_lock_time=lock_time, capture_before_lock=True, evaluation_shape=outcome_shape,
        metric=metric, diversity=diversity, effective_auto_cap=selected.attrs['effective_auto_cap_pct'],
        candidate_rows=len(raw_candidates), unique_candidates=len(roster_keys), duplicate_candidate_rows=duplicate_candidates,
        actual_entries=len(standings), captured_field_size=contest['field_size'],
        captured_size_minus_actual=int(contest['field_size'])-len(standings),
        captured_opponent_rows=len(field), actual_opponents=len(opponents),
        actual_field_summary=actual_field, simulated_field_summary=simulated_field,
        published_rank_reconciliation=True, payout_pool_reconciliation=True,
        captured_salary_and_roster_constraints_pass=True,
        unavailable_opponent_rosters=unavailable, portfolio_entries=count,
        replay_matches_entered=Counter(selected_keys)==Counter(entered),
        fees=fees, entered_winnings=entered_winnings, entered_roi_pct=entered_roi,
        replay_winnings=replay_winnings, replay_roi_pct=replay_roi,
        random_draws=draws, random_attempts=attempts, seed=seed,
        random_roi_mean=float(random_roi.mean()), random_roi_median=float(np.median(random_roi)),
        random_roi_p05=float(np.quantile(random_roi,.05)), random_roi_p95=float(np.quantile(random_roi,.95)),
        replay_one_sided_mc_p=(1+int(np.count_nonzero(random_winnings>=replay_winnings-1e-9)))/(draws+1),
        entered_one_sided_mc_p=(1+int(np.count_nonzero(random_winnings>=entered_winnings-1e-9)))/(draws+1),
        random_roi_histogram=dict(counts=histogram_counts.tolist(), edges=histogram_edges.tolist(),
            portfolios_above_100_pct=int(np.count_nonzero(random_roi>100))), warnings=warnings)
