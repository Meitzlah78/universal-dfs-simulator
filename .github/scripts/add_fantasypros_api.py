from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text(encoding="utf-8")

old = '''            result = {}
            is_fd = "fanduel" in str(platform_name).casefold()
            scoring = "HALF" if is_fd else "PPR"
            for position in ("QB", "RB", "WR", "TE", "K", "DST"):
                response = requests.get(
                    f"https://api.fantasypros.com/public/v2/json/nfl/{season}/projections",
                    headers={"x-api-key": api_key, "Accept": "application/json"},
                    params={"position": position, "scoring": scoring},
                    timeout=(5, 30),
                )
'''
new = '''            result = {}
            is_fd = "fanduel" in str(platform_name).casefold()
            scoring = "HALF" if is_fd else "PPR"
            projection_week = None
            for position in ("QB", "RB", "WR", "TE", "K", "DST"):
                # R2P is FantasyPros' weekly rankings-to-projections feed. With
                # no explicit week it selects the next available weekly slate.
                # Team positions cannot use R2P, so reuse the week returned by
                # the skill-position response for K/DST.
                if position in ("K", "DST"):
                    params = {"position": position}
                    if projection_week is not None:
                        params["week"] = projection_week
                else:
                    params = {"position": position, "r2p": "true"}
                response = requests.get(
                    f"https://api.fantasypros.com/public/v2/json/nfl/{season}/projections",
                    headers={"x-api-key": api_key, "Accept": "application/json"},
                    params=params,
                    timeout=(5, 30),
                )
'''
if old not in s:
    if 'params = {"position": position, "r2p": "true"}' in s:
        print("FantasyPros R2P request already applied")
        raise SystemExit(0)
    raise SystemExit("FantasyPros request loop not found")
s = s.replace(old, new, 1)

old_payload = '''                payload = response.json()
                players = payload.get("players", []) if isinstance(payload, dict) else []
'''
new_payload = '''                payload = response.json()
                if isinstance(payload, dict) and projection_week is None:
                    try:
                        returned_week = int(payload.get("week"))
                        if returned_week > 0:
                            projection_week = returned_week
                    except (TypeError, ValueError):
                        pass
                players = payload.get("players", []) if isinstance(payload, dict) else []
'''
if old_payload not in s:
    raise SystemExit("FantasyPros payload block not found")
s = s.replace(old_payload, new_payload, 1)

p.write_text(s, encoding="utf-8")
print("FantasyPros weekly R2P projections applied")
