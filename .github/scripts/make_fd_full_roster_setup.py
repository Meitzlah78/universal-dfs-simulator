from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel only. DraftKings is intentionally untouched.
# Add automatic NWS weather lookup for FanDuel Full Roster and Single Game.
helper = r'''

FD_STADIUM_WEATHER = {
    "ARI": (33.5276, -112.2626, True), "ATL": (33.7554, -84.4008, True),
    "BAL": (39.2780, -76.6227, False), "BUF": (42.7738, -78.7870, False),
    "CAR": (35.2258, -80.8528, False), "CHI": (41.8623, -87.6167, False),
    "CIN": (39.0955, -84.5161, False), "CLE": (41.5061, -81.6995, False),
    "DAL": (32.7473, -97.0945, True), "DEN": (39.7439, -105.0201, False),
    "DET": (42.3400, -83.0456, True), "GB": (44.5013, -88.0622, False),
    "HOU": (29.6847, -95.4107, True), "IND": (39.7601, -86.1639, True),
    "JAX": (30.3239, -81.6373, False), "KC": (39.0489, -94.4839, False),
    "LV": (36.0908, -115.1830, True), "LAC": (33.9535, -118.3392, True),
    "LAR": (33.9535, -118.3392, True), "MIA": (25.9580, -80.2389, False),
    "MIN": (44.9736, -93.2575, True), "NE": (42.0909, -71.2643, False),
    "NO": (29.9511, -90.0812, True), "NYG": (40.8135, -74.0745, False),
    "NYJ": (40.8135, -74.0745, False), "PHI": (39.9008, -75.1675, False),
    "PIT": (40.4468, -80.0158, False), "SEA": (47.5952, -122.3316, False),
    "SF": (37.4030, -121.9700, False), "TB": (27.9759, -82.5033, False),
    "TEN": (36.1665, -86.7713, False), "WAS": (38.9076, -76.8645, False),
}

def _fd_parse_wind_mph(value):
    nums = re.findall(r"\\d+(?:\\.\\d+)?", str(value or ""))
    return max([float(x) for x in nums], default=0.0)

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_fd_nws_weather(team):
    info = FD_STADIUM_WEATHER.get(str(team).upper().strip())
    if not info:
        return None
    lat, lon, dome = info
    if dome:
        return {"wind_mph": 0.0, "precip_pct": 0.0, "heavy_snow": False, "dome": True, "summary": "Indoor/dome"}
    headers = {"User-Agent": "UniversalDFSSimulator/1.0 (GitHub Meitzlah78/universal-dfs-simulator)", "Accept": "application/geo+json"}
    try:
        point = requests.get(f"https://api.weather.gov/points/{lat},{lon}", headers=headers, timeout=8)
        point.raise_for_status()
        hourly_url = point.json().get("properties", {}).get("forecastHourly")
        if not hourly_url:
            return None
        forecast = requests.get(hourly_url, headers=headers, timeout=8)
        forecast.raise_for_status()
        periods = forecast.json().get("properties", {}).get("periods", [])
        if not periods:
            return None
        # FanDuel templates do not reliably expose an exact kickoff timestamp in the player table.
        # Use the strongest meaningful conditions in the next 7 days so weather is not silently ignored.
        periods = periods[:168]
        winds = [_fd_parse_wind_mph(p.get("windSpeed")) for p in periods]
        pops = [float((p.get("probabilityOfPrecipitation") or {}).get("value") or 0.0) for p in periods]
        snow = any("snow" in str(p.get("shortForecast", "")).lower() for p in periods)
        idx = int(np.argmax(np.asarray(winds) + np.asarray(pops) / 20.0)) if periods else 0
        p = periods[idx]
        wind = winds[idx] if winds else 0.0
        pop = pops[idx] if pops else 0.0
        summary = str(p.get("shortForecast") or "NWS forecast")
        return {"wind_mph": wind, "precip_pct": pop, "heavy_snow": snow, "dome": False, "summary": summary}
    except Exception:
        return None

def apply_fd_nws_weather(fd_players):
    frame = fd_players.copy()
    weather_by_team = {}
    for team in sorted(set(frame.get("Team", pd.Series(dtype=str)).astype(str).str.upper())):
        weather_by_team[team] = fetch_fd_nws_weather(team)
    def _mult(row):
        wx = weather_by_team.get(str(row.get("Team", "")).upper())
        if not wx:
            return 1.0
        return fd_weather_multiplier(row.get("Position", ""), wx["wind_mph"], wx["precip_pct"], wx["heavy_snow"], wx["dome"])
    frame["Weather Mult"] = frame.apply(_mult, axis=1)
    frame["Projection"] = pd.to_numeric(frame["Projection"], errors="coerce") * frame["Weather Mult"]
    frame["Weather"] = frame["Team"].astype(str).str.upper().map(lambda t: (weather_by_team.get(t) or {}).get("summary", "Unavailable"))
    frame["Wind MPH"] = frame["Team"].astype(str).str.upper().map(lambda t: (weather_by_team.get(t) or {}).get("wind_mph", 0.0))
    frame["Precip %"] = frame["Team"].astype(str).str.upper().map(lambda t: (weather_by_team.get(t) or {}).get("precip_pct", 0.0))
    return frame
'''

if "def fetch_fd_nws_weather(" not in text:
    anchor = 'if platform == "FanDuel":'
    idx = text.find(anchor)
    if idx == -1:
        raise SystemExit("FanDuel branch not found")
    text = text[:idx] + helper + "\n" + text[idx:]

# Replace the earlier passive weather-column block with the automatic NWS lookup.
start_token = '    # FanDuel weather adjustment: applies to both Full Roster and Single Game when weather data is available.'
end_token = '    st.write("### Build Settings")'
start = text.find(start_token, text.find('if platform == "FanDuel":'))
end = text.find(end_token, start)
if start == -1 or end == -1:
    raise SystemExit("FanDuel weather block not found")
replacement = '''    # Automatic NWS weather for FanDuel Full Roster and Single Game only.\n    fd_players = apply_fd_nws_weather(fd_players)\n    _fd_weather_impacts = fd_players[pd.to_numeric(fd_players.get("Weather Mult", 1.0), errors="coerce").fillna(1.0).ne(1.0)] if "Weather Mult" in fd_players.columns else pd.DataFrame()\n    if not _fd_weather_impacts.empty:\n        st.caption("FanDuel weather adjustments active from National Weather Service forecasts.")\n\n'''
text = text[:start] + replacement + text[end:]

path.write_text(text, encoding="utf-8")
