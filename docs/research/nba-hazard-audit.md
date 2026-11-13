# NBA shooting-foul/rebound hazard checkpoint

Offline/draft only. Freeze corrected clock parameters, target rotations/minutes sampler, role/shooting priors, coaching rules and archive blending. Preserve the original unsupported roster case as excluded/unresolved.

Four arms, 128 simulations per game/arm, same 226-game comparison set. Every arm completes; no new failures. The reference reproduces all saved per-game points/FGA/FTA/shooting-foul/player-OREB means exactly. 904 unique arm/game rows are retained through checkpoint/resume.

| Per game | Actual | Clock reference | Foul fit | Rebound fit | Combined |
|---|---:|---:|---:|---:|---:|
| Points | 227.35 | 251.81 | 250.86 | 255.79 | 255.18 |
| FGA | 175.48 | 181.61 | 188.35 | 184.38 | 191.46 |
| FTA | 52.00 | 62.41 | 51.69 | 63.58 | 52.75 |
| Shooting fouls | 21.31 | 27.62 | 24.20 | 28.06 | 24.62 |
| Player OREB | 24.20 | 26.01 | 26.69 | 24.68 | 25.47 |
| Player DREB | 64.19 | 75.14 | 77.13 | 64.92 | 66.60 |
| Derived FGM | 80.20 | 87.26 | 90.49 | 88.57 | 91.95 |

The no-basket foul probability is fitted per potential shot opportunity (FGA plus normal shooting fouls), separately from matched and-one probability per made basket. Incumbent values are 12.11% / 3.00%; descriptive source values are 8.66% / 5.73%. Replay fits use earlier dates only and 100 incumbent pseudo-exposures, not pooled future targets. Normal-foul probability log loss improves 0.300730→0.294700 on observed exposures, but this does not establish full-game calibration.

Rebounds are four-way outcomes (player OREB/DREB, team OREB/DREB), separately fit after FG misses and final nontechnical FT misses. Non-final FT misses are excluded. Team rebounds do not award fantasy player rebound points; team retention is not identical to player OREB. Special retained-ball FT/rim-contact/backcourt reset contexts remain approximate; no complete-rule claim is made.

No positive rebound delay is identifiable in the saved feed: all 21,724 resolved miss/rebound pairs on the comparison set (18,746 player; 2,978 team) have zero recorded game-clock gap. This does not establish zero physical flight time. No assumed 1.5–2.5 second padding is added. Trimming DREB time would speed games up; the previous excess DREB clock total is substantially a counting issue (about 75 modeled player DREB vs 64 in PBP), while per-interval timing is already slightly shorter.

Lower shooting-foul probability reallocates opportunities to FGA, so it does not simply remove FT points. The foul-only FTA match therefore does not satisfy the joint points/FGA/FTA checkpoint. Restoring team rebound outcomes changes retention and can increase shots while correcting player credits. **No tested arm satisfies the joint gate.** Do not advance to minutes dispersion or player-role blending, and do not promote.

All 399 NBA tests run with one skip and no failures. Twelve focused hazard/clock/integration/checkpoint checks pass. Regulation ledgers conserve 2,880 seconds. Input source hashes and prior-date cutoffs are checked; interrupted replays resume per-game from atomic checkpoints without rerunning completed arms. Default behavior stays unchanged unless explicit research hazard parameters are supplied.

Reproduce:

```
python scripts/audit_nba_hazards.py REPO EVIDENCE OBSERVED.json
python scripts/check_nba_hazard_probabilities.py REPO EVIDENCE PROBABILITIES.json
python scripts/replay_nba_hazard_audit.py REPO EVIDENCE OUTPUT
```

The OUTPUT directory may contain its previous checkpoint. Duplicate or mismatched-date rows are rejected; completed arm/game rows are preserved. These are development conditional mechanics results using observed rosters/minutes, not fresh pregame holdout evidence or new eight-build coverage results.
