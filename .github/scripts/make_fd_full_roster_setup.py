from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

# FanDuel only. DraftKings is intentionally untouched.
# Weather adjustment helper for both FanDuel Full Roster and Single Game.
weather_helper = r'''
def fd_weather_multiplier(position, wind_mph=0.0, precip_pct=0.0, heavy_snow=False, dome=False):
    """Conservative FanDuel weather adjustment. Dome/closed-roof games stay neutral."""
    if dome:
        return 1.0
    pos = str(position).upper().strip()
    wind = max(float(wind_mph or 0.0), 0.0)
    precip = max(float(precip_pct or 0.0), 0.0)
    mult = 1.0
    # Wind is the primary weather signal. Keep mild weather essentially neutral.
    if wind >= 20:
        if pos in {"QB", "WR", "TE"}: mult *= 0.90
        elif pos in {"K"}: mult *= 0.86
        elif pos in {"RB"}: mult *= 1.02
    elif wind >= 15:
        if pos in {"QB", "WR", "TE"}: mult *= 0.95
        elif pos in {"K"}: mult *= 0.94
        elif pos in {"RB"}: mult *= 1.01
    elif wind >= 10:
        if pos in {"QB", "WR", "TE"}: mult *= 0.985
        elif pos in {"K"}: mult *= 0.98
    # Only meaningful precipitation gets an additional adjustment.
    if precip >= 60:
        if pos in {"QB", "WR", "TE"}: mult *= 0.97
        elif pos in {"RB"}: mult *= 1.01
        elif pos in {"K"}: mult *= 0.97
    if heavy_snow:
        if pos in {"QB", "WR", "TE"}: mult *= 0.92
        elif pos in {"RB"}: mult *= 1.02
        elif pos in {"K"}: mult *= 0.90
    return float(np.clip(mult, 0.75, 1.08))
'''

# Add helper once before the FanDuel branch. It is inert unless FanDuel weather columns/data exist.
if "def fd_weather_multiplier(" not in text:
    anchor = 'if platform == "FanDuel":'
    idx = text.find(anchor)
    if idx == -1:
        raise SystemExit("FanDuel branch not found")
    text = text[:idx] + weather_helper + "\n" + text[idx:]

# Apply weather to FanDuel player projections/means when weather data is present in the FD pool.
# Supports future/live columns without breaking current salary templates.
weather_apply = r'''
    # FanDuel weather adjustment: applies to both Full Roster and Single Game when weather data is available.
    _fd_wind_col = next((c for c in ["Wind MPH", "Wind", "WindSpeed", "Wind Speed"] if c in fd_players.columns), None)
    _fd_precip_col = next((c for c in ["Precip %", "Precipitation %", "Rain %", "Precip"] if c in fd_players.columns), None)
    _fd_dome_col = next((c for c in ["Dome", "Indoor", "Roof Closed"] if c in fd_players.columns), None)
    _fd_snow_col = next((c for c in ["Heavy Snow", "Snow"] if c in fd_players.columns), None)
    if _fd_wind_col or _fd_precip_col or _fd_dome_col or _fd_snow_col:
        def _fd_weather_row(row):
            wind = pd.to_numeric(pd.Series([row.get(_fd_wind_col, 0) if _fd_wind_col else 0]), errors="coerce").fillna(0).iloc[0]
            precip = pd.to_numeric(pd.Series([row.get(_fd_precip_col, 0) if _fd_precip_col else 0]), errors="coerce").fillna(0).iloc[0]
            dome_raw = row.get(_fd_dome_col, False) if _fd_dome_col else False
            snow_raw = row.get(_fd_snow_col, False) if _fd_snow_col else False
            dome = str(dome_raw).strip().lower() in {"1", "true", "yes", "y", "closed", "indoor"}
            snow = str(snow_raw).strip().lower() in {"1", "true", "yes", "y", "heavy"}
            return fd_weather_multiplier(row.get("Position", ""), wind, precip, snow, dome)
        fd_players["Weather Mult"] = fd_players.apply(_fd_weather_row, axis=1)
        fd_players["Projection"] = pd.to_numeric(fd_players["Projection"], errors="coerce").fillna(0.0) * fd_players["Weather Mult"]
'''
if "# FanDuel weather adjustment: applies to both Full Roster and Single Game" not in text:
    # Insert immediately before FanDuel build settings, after fd_players has been created.
    anchors = ['    st.write("### Build Settings")', '    st.subheader("Build Settings")']
    insert_at = -1
    for anchor in anchors:
        insert_at = text.find(anchor, text.find('if platform == "FanDuel":'))
        if insert_at != -1:
            break
    if insert_at == -1:
        raise SystemExit("FanDuel Build Settings anchor not found")
    text = text[:insert_at] + weather_apply + "\n" + text[insert_at:]

path.write_text(text, encoding="utf-8")
