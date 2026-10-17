from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text(encoding="utf-8")

old = '''            for position in ("QB", "RB", "WR", "TE", "K", "DST"):
                params = {"position": position, "week": projection_week, "scoring": scoring}
                response = requests.get(
                    f"https://api.fantasypros.com/public/v2/json/nfl/{season}/projections",
                    headers={"x-api-key": api_key, "Accept": "application/json"},
                    params=params,
                    timeout=(5, 30),
                )
                response.raise_for_status()
                payload = response.json()
                players = payload.get("players", []) if isinstance(payload, dict) else []
                for player in players:
                    if not isinstance(player, dict):
                        continue
                    name = player.get("name") or player.get("player_name")
                    key = normalize_projection_player_name(name)
                    if not key or (target_keys and key not in target_keys):
                        continue
                    stats = player.get("stats") or {}
                    # FantasyPros currently returns stats as a one-item list for
                    # NFL projections. Older responses used a dict, so support both.
                    if isinstance(stats, list):
                        stats = next((item for item in stats if isinstance(item, dict)), {})
                    if not isinstance(stats, dict):
                        stats = {}
                    candidates = (
                        ("points_half", "fpts_half", "fantasy_points_half", "fpts")
                        if is_fd else
                        ("points_ppr", "fpts_ppr", "fantasy_points_ppr", "fpts")
                    )
                    value = next((stats.get(k) for k in candidates if stats.get(k) is not None), None)
                    if value is None:
                        value = stats.get("points")
                    if value is None:
                        value = player.get("fpts") or player.get("points") or player.get("projection")
                    try:
                        value = float(value)
                    except (TypeError, ValueError):
                        continue
                    if np.isfinite(value) and value >= 0:
                        result[key] = value
            return result
'''

new = '''            fp_diag = []
            fp_matched_names = []
            for position in ("QB", "RB", "WR", "TE", "K", "DST"):
                params = {"position": position, "week": projection_week, "scoring": scoring}
                response = requests.get(
                    f"https://api.fantasypros.com/public/v2/json/nfl/{season}/projections",
                    headers={"x-api-key": api_key, "Accept": "application/json"},
                    params=params,
                    timeout=(5, 30),
                )
                response.raise_for_status()
                payload = response.json()
                players = payload.get("players", []) if isinstance(payload, dict) else []
                raw_count = len(players) if isinstance(players, list) else 0
                target_name_count = 0
                parsed_target_count = 0
                sample_stats_keys = []
                for player in players:
                    if not isinstance(player, dict):
                        continue
                    name = player.get("name") or player.get("player_name")
                    key = normalize_projection_player_name(name)
                    if not key or (target_keys and key not in target_keys):
                        continue
                    target_name_count += 1
                    stats = player.get("stats") or {}
                    if isinstance(stats, list):
                        stats = next((item for item in stats if isinstance(item, dict)), {})
                    if not isinstance(stats, dict):
                        stats = {}
                    if not sample_stats_keys:
                        sample_stats_keys = list(stats.keys())[:12]
                    candidates = (
                        ("points_half", "fpts_half", "fantasy_points_half", "fpts")
                        if is_fd else
                        ("points_ppr", "fpts_ppr", "fantasy_points_ppr", "fpts")
                    )
                    value = next((stats.get(k) for k in candidates if stats.get(k) is not None), None)
                    if value is None:
                        value = stats.get("points")
                    if value is None:
                        value = player.get("fpts") or player.get("points") or player.get("projection")
                    try:
                        value = float(value)
                    except (TypeError, ValueError):
                        continue
                    if np.isfinite(value) and value >= 0:
                        result[key] = value
                        parsed_target_count += 1
                        fp_matched_names.append(str(name))
                fp_diag.append(
                    f"{position}: raw {raw_count}, slate names {target_name_count}, parsed {parsed_target_count}"
                    + (f", stats keys {sample_stats_keys}" if target_name_count and parsed_target_count == 0 else "")
                )
            st.caption(
                f"FantasyPros diagnostic — week {projection_week}; "
                + " | ".join(fp_diag)
                + "; matched: "
                + (", ".join(fp_matched_names) if fp_matched_names else "none")
            )
            return result
'''

if old not in s:
    if "FantasyPros diagnostic — week" in s:
        print("FantasyPros diagnostics already applied")
        raise SystemExit(0)
    raise SystemExit("FantasyPros projection loop not found")

s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("FantasyPros runtime diagnostics applied")
