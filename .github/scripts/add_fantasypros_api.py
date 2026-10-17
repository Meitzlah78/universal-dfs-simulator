from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text(encoding="utf-8")

old = '''            response = requests.get(
                f"https://api.fantasypros.com/public/v2/json/nfl/{season}/projections",
                headers={"x-api-key": api_key, "Accept": "application/json"},
                params={"positions": "QB:RB:WR:TE:K:DST", "scoring": "PPR"},
                timeout=(5, 30),
            )
            response.raise_for_status()
            payload = response.json()
            players = payload.get("players", []) if isinstance(payload, dict) else []
            result = {}
            is_fd = "fanduel" in str(platform_name).casefold()
            for player in players:
                if not isinstance(player, dict):
                    continue
                name = player.get("name") or player.get("player_name")
                key = normalize_projection_player_name(name)
                if not key or (target_keys and key not in target_keys):
                    continue
                stats = player.get("stats") or {}
                if not isinstance(stats, dict):
                    stats = {}
                candidates = (
                    ("points_half", "fpts_half", "fantasy_points_half")
                    if is_fd else
                    ("points_ppr", "fpts_ppr", "fantasy_points_ppr")
                )
                value = next((stats.get(k) for k in candidates if stats.get(k) is not None), None)
                if value is None:
                    value = stats.get("points")
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    continue
                if np.isfinite(value) and value >= 0:
                    result[key] = value
            return result
'''

new = '''            # FantasyPros serves NFL projections by position. Pull each position
            # separately and request the current weekly projections so Single Game
            # slates are not limited to a couple of players from a default response.
            result = {}
            is_fd = "fanduel" in str(platform_name).casefold()
            scoring = "HALF" if is_fd else "PPR"
            for position in ("QB", "RB", "WR", "TE", "K", "DST"):
                response = requests.get(
                    f"https://api.fantasypros.com/public/v2/json/nfl/{season}/projections",
                    headers={"x-api-key": api_key, "Accept": "application/json"},
                    params={"position": position, "week": "current", "scoring": scoring},
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

if old not in s:
    if 'params={"position": position, "week": "current", "scoring": scoring}' in s:
        print("FantasyPros weekly position fix already applied")
        raise SystemExit(0)
    raise SystemExit("FantasyPros request block not found")

s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("FantasyPros weekly position fix applied")
