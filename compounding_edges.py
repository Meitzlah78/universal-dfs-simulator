import math
import re
import requests

BASE_URL = "https://www.compoundingedges.com/api/v1/nfl"


def normalize_name(value):
    text = str(value or "").casefold().strip()
    text = re.sub(r"\s+(jr|sr|ii|iii|iv|v)\.?$", "", text)
    return re.sub(r"[^a-z0-9]", "", text)


def records(payload, keys):
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def fetch_projections(token, platform_name, target_names=None, slate_date=None, timeout=30):
    token = str(token or "").strip()
    if not token:
        return {}, "missing token"
    headers = {"Accept": "application/json", "Authorization": "Bearer " + token}
    site = "fanduel" if "fanduel" in str(platform_name).casefold() else "draftkings"
    targets = {normalize_name(x) for x in (target_names or []) if normalize_name(x)}
    params = {"date": slate_date} if slate_date else {}
    response = requests.get(BASE_URL + "/slates", headers=headers, params=params, timeout=timeout)
    response.raise_for_status()
    slates = records(response.json(), ("slates", "data", "results"))
    best = {}
    best_id = None
    best_overlap = -1
    for slate in slates:
        hay = " ".join(str(slate.get(k, "")) for k in ("site", "platform", "operator", "provider", "name")).casefold()
        if hay and site not in hay.replace(" ", ""):
            continue
        slate_id = slate.get("id") or slate.get("slate_id") or slate.get("slateId")
        if slate_id is None:
            continue
        projection_response = requests.get(BASE_URL + "/projections", headers=headers, params={"slate_id": slate_id}, timeout=timeout)
        if projection_response.status_code in (400, 404, 422):
            continue
        projection_response.raise_for_status()
        rows = records(projection_response.json(), ("projections", "players", "data", "results"))
        values = {}
        for row in rows:
            name = row.get("player_name") or row.get("name") or row.get("full_name")
            player = row.get("player")
            if not name and isinstance(player, dict):
                name = player.get("name") or player.get("full_name")
            key = normalize_name(name)
            if not key or (targets and key not in targets):
                continue
            candidates = ("fanduel_points", "fd_points") if site == "fanduel" else ("draftkings_points", "dk_points")
            candidates += ("fantasy_points", "projected_points", "projection", "fpts", "points", "mean", "median")
            value = None
            for field in candidates:
                raw = row.get(field)
                try:
                    raw = float(raw)
                except (TypeError, ValueError):
                    continue
                if math.isfinite(raw) and raw > 0:
                    value = raw
                    break
            if value is not None:
                values[key] = value
        overlap = len(targets.intersection(values)) if targets else len(values)
        if overlap > best_overlap:
            best, best_overlap, best_id = values, overlap, slate_id
    return best, "slate " + str(best_id) if best else "no matching projections"
