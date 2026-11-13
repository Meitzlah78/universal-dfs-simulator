# NBA guided candidate search: fixed offline comparison

November 13, 2026. Research only. No promotion, production import or changes to salary floor, outcome arrays, minutes, player projections, ownership, field, payouts or PR #78 selection policy. These are the same two development dates, not fresh holdouts. Three search seeds are not six independent slates.

## Frozen policy

- Baseline: current-main scenario-score heuristic, extra correlation 0.
- Correlation arm: identical generator, extra correlation 25; existing positive same-game Pearson threshold remains .05.
- Environment arm: correlation 0; on 35% of proposals choose a focus game using softmax((game total − mean total)/15 − absolute implied team difference/10). Add .25 × proposal score standard deviation to players from that game. This is a soft preference, not a forced stack count; 65% of proposals remain unfocused. A separate RNG stream preserves the underlying scenario/noise draw stream.
- All arms: $58,000 floor, $60,000 cap, 5,000 candidates, 200,000 max attempts, original salary-aware setting, search seeds 84/184/284. Same construction draws (seed 83), independent evaluation draws (2100), field multiplicities and payouts. Candidate scoring does not use actual outcomes. The parameter file was written before evaluating challengers and was not tuned to winners.

## Results: means across three fixed search seeds

| Slate | Arm | Mean best actual candidate | Mean best selected actual | Exact winner entries | 400+ / 370+ candidate entries |
|---|---|---:|---:|---:|---:|
| Nov. 7 | baseline | 379.83 | 362.93 | 0 / 3 pools | 0 |
| Nov. 7 | correlation25 | 379.83 | 362.93 | 0 / 3 pools | 0 |
| Nov. 7 | environment | 380.20 | 362.93 | 0 / 3 pools | 0 |
| Nov. 10 | baseline | 331.77 | 305.63 | 0 / 3 pools | 0 |
| Nov. 10 | correlation25 | 331.77 | 305.63 | 0 / 3 pools | 0 |
| Nov. 10 | environment | 332.20 | 304.13 | 0 / 3 pools | 0 |

All 18 arm/game/seed runs reach 5,000 unique legal candidates: 90,000 candidate appearances, fully scored against uploaded contest player FPTS. Each selected portfolio has 20 unique entries, independently validated hard caps and no more than 5% measured quality loss. Source manifests are hash checked; construction/evaluation outcome hashes remain unchanged. Checkpoints preserve completed arms and selection player IDs are retained. Baseline arrays are checked against the unchanged live generator for every seed.

No arm generates either exact winning roster or any 400+ candidate on Nov. 7 / 370+ candidate on Nov. 10. These realized scores are retrospective grading, not a search objective. Environment guidance slightly increases mean pool maxima (+0.37 and +0.43), leaves Nov. 7's selected maxima unchanged and lowers Nov. 10's mean selected maximum by 1.50 points. It does not justify promotion.

## Why correlation 25 is exactly unchanged

- 136378: 135 eligible players, **0 same-game positive pairs at .05**, maximum same-game correlation 0.04338.
- 136535: 104 eligible players, **0 same-game positive pairs at .05**, maximum same-game correlation 0.03464.

The bonus matrix is therefore all zero on these saved construction draws. Candidate IDs/slot orders are byte-identical between baseline and correlation25 on every seed. This does not mean all game outcomes are independent or the correct response is to lower the noise threshold until the knob activates. Shared pace and competition for usage can produce weak or negative pairwise correlations, and linear correlation alone does not measure joint tail dependence. Validate empirical dependence before changing its threshold or forcing higher correlation.

## The winner was not necessarily a high-total game stack

Nov. 7 GS–ORL had a saved game total of 220, the lowest on that six-game slate. It receives 11.46% of focus draws versus 16.67% under uniform game focus; POR–SA at 229.5 receives 26.37%. Nov. 10's MIA–UTA was the highest total at 228, but a 9-point implied margin reduces its focus weight to 21.29%; LAC–PHO at 224.5 with a 3.5-point margin receives 29.22%. The fixed policy does not know the realized winning environment. Retrospectively forcing those winning games would invalidate this comparison.

The absence of winners in these limited heuristic proposals does not prove that player tails or team totals alone are wrong. Earlier diagnostics found Nov. 10's winner hypothetically ranked ninth under the saved evaluator, which supports investigating global roster-combination search. It does not certify the full simulator's calibration or guarantee selection under caps. A meaningful next isolated challenger is stronger combination optimization on unchanged joint scenarios, rather than increasing a correlation bonus whose current matrix is zero or forcing stacks from hindsight.

## DraftDashboard input clarification

The user supplied tooltips defining MIN as minutes played per game (historical), USE as usage while on the floor, and OWN as projected main-slate DFS ownership. MIN must not be silently relabeled as tonight's projected minutes. This experiment uses the original saved RotoWire **Projected Minutes** inputs, unchanged; it does not import historical DD MIN as a projection. The current DD uploader handles ownership and does not overwrite point projections/minutes. Site/date/main-slate ownership scope must match the slate. Further supplied tooltips identify the icon columns as DashRank (100), opponent team defensive rank (30), and opponent positional defensive rank (30), separate from 47.89 projected points and 48.03% projected ownership. Rank direction is not assumed from the numeric labels alone. These proprietary ratings were not used as fantasy-point projections or unvalidated extra multipliers.

## Limitations and decision

Keep both guidance arms offline. No defaults, salary floors, core mechanics or exposure settings were changed. No inference of reliable live profit, significance, complete calibration or universal anti-stack behavior is supported by two development dates. The comparator tests portfolio predicted quality while actual-best scores describe one realized result; they are not interchangeable objectives.

The focused suite ran 15 tests with no failures. It covers disabled-policy equality, outcome immutability, legal unique rosters, bounded parameters, market validation, hard caps and timeout recovery. This is not a new full-app test suite claim. Production has no imports of the challenger.

## Reproduction

```
PYTHONPATH=.:tests python scripts/replay_nba_guided_search_offline.py WORKSPACE 136378 84
# Repeat 184/284 and 136535 using the frozen policy and same source archives.
```

The scoped script expects nba-selector-evidence and nba-selector-standings under WORKSPACE plus nba-guided-search-results/policy.json. It resumes completed arm rows. Source archives and full outcome arrays are not duplicated in this report. Raw per-seed records, policy, game weights, selected IDs and candidate index archives are provided for review.
