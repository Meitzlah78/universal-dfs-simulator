from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
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
    # The API requires a date and canonical slate fields, not a slate ID.
    # Include upcoming days when the salary slate is for the next NFL game.
    today = datetime.now(ZoneInfo("America/New_York")).date()
    dates = [slate_date] if slate_date else [
        (today + timedelta(days=offset)).isoformat() for offset in range(4)
    ]
    slate_type = "Showdown" if any(
        label in str(platform_name).casefold() for label in ("showdown", "single game")
    ) else "Classic"
    slates = []
    for date in dates:
        response = requests.get(BASE_URL + "/slates", headers=headers,
                                params={"date": date}, timeout=timeout)
        response.raise_for_status()
        slates.extend(records(response.json(), ("slates", "data", "results")))
    best = {}
    best_id = None
    best_overlap = -1
    requested = set()
    for slate in slates:
        if str(slate.get("site", "")).casefold() != site:
            continue
        if slate.get("slate_type") != slate_type:
            continue
        fields = ("site", "slate_type", "slate_name", "start_time")
        if not all(slate.get(field) for field in fields):
            continue
        identity = tuple(slate[field] for field in fields)
        if identity in requested:
            continue
        # Four date requests plus at most eight projection requests respect the
        # documented 12-request/minute budget for one refresh.
        if len(requested) >= 8:
            break
        requested.add(identity)
        projection_response = requests.get(
            BASE_URL + "/projections", headers=headers,
            params={field: slate[field] for field in fields}, timeout=timeout,
        )
        if projection_response.status_code in (404, 503):
            continue
        projection_response.raise_for_status()
        slate_id = str(slate["slate_name"]) + " " + str(slate["start_time"])
        rows = records(projection_response.json(), ("projections", "players", "data", "results"))
        values = {}
        rows = sorted(rows, key=lambda row: str(row.get("roster_position", "")).upper() in ("CPT", "CAPTAIN", "MVP", "MVP 1.5X"))
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
            if value is not None and key not in values:
                values[key] = value
        overlap = len(targets.intersection(values)) if targets else len(values)
        if overlap > best_overlap:
            best, best_overlap, best_id = values, overlap, slate_id
    return best, "slate " + str(best_id) if best else "no matching projections"
