from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text(encoding="utf-8")

old = '''            result = {}
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
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict) and projection_week is None:
                    try:
                        returned_week = int(payload.get("week"))
                        if returned_week > 0:
                            projection_week = returned_week
                    except (TypeError, ValueError):
                        pass
'''
new = '''            result = {}
            is_fd = "fanduel" in str(platform_name).casefold()
            scoring = "HALF" if is_fd else "PPR"

            # Ask FantasyPros for its current NFL week first, then request the
            # normal expert projection feed for that exact week. R2P is based on
            # weekly rankings and is intentionally much thinner than the full
            # projections feed, which caused Single Game slates to match only a
            # handful of players.
            projection_week = None
            try:
                week_response = requests.get(
                    "https://api.fantasypros.com/public/v2/json/nfl/players",
                    headers={"x-api-key": api_key, "Accept": "application/json"},
                    timeout=(5, 30),
                )
                week_response.raise_for_status()
                week_payload = week_response.json()
                if isinstance(week_payload, dict):
                    returned_week = int(week_payload.get("week") or 0)
                    if returned_week > 0:
                        projection_week = returned_week
            except Exception:
                projection_week = None

            # Safe fallback for the active season if the metadata endpoint does
            # not publish a current week. This keeps the projection request out
            # of week 0/preseason while allowing the API response to correct it.
            if projection_week is None:
                now_et = datetime.now(ZoneInfo("America/New_York"))
                season_start = datetime(season, 9, 13, tzinfo=ZoneInfo("America/New_York"))
                projection_week = max(1, min(18, ((now_et.date() - season_start.date()).days // 7) + 1))

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
'''
if old not in s:
    if 'normal expert projection feed for that exact week' in s:
        print("FantasyPros explicit-week projections already applied")
        raise SystemExit(0)
    raise SystemExit("FantasyPros R2P request block not found")
s = s.replace(old, new, 1)

p.write_text(s, encoding="utf-8")
print("FantasyPros explicit current-week projections applied")
