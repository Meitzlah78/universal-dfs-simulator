from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text()
import_anchor = "import numpy as np\n"
import_line = "from dk_showdown_engine import candidate_score as dk_showdown_candidate_score\n"
if import_line not in text:
    if import_anchor not in text:
        raise SystemExit("SAFE_ABORT: numpy import anchor not found")
    text = text.replace(import_anchor, import_anchor + import_line, 1)

start_anchor = "                total_mean = (\n"
end_anchor = "                captain_candidates.append({\n"
score_header = text.index("                # SIMULATION SCORE\n")
start = text.index(start_anchor, score_header)
end = text.index(end_anchor, start)
legacy = text[start:end]
required = ["total_p95 = (", "total_p99 = (", "raw_score = (", "lineup_ownership = (", "ownership_tax =", "score = raw_score - ownership_tax + upside_credit"]
if not all(token in legacy for token in required):
    raise SystemExit("SAFE_ABORT: candidate scoring block did not match expected legacy structure")
new = '''                _candidate_metrics = dk_showdown_candidate_score(
                    captain,
                    flex_players,
                    player_sim,
                    {name: float(showdown_ownership_proxy[index]) for name, index in ownership_index.items()},
                    P95_WEIGHT,
                    P99_WEIGHT,
                    MEAN_WEIGHT,
                    STDDEV_WEIGHT,
                )
                total_mean = _candidate_metrics["SimMean"]
                total_p95 = _candidate_metrics["SimP95"]
                total_p99 = _candidate_metrics["SimP99"]
                score = _candidate_metrics["Score"]

'''
path.write_text(text[:start] + new + text[end:])
