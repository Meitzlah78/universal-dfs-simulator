from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

old = '''@st.fragment(run_every="30m")
def automatic_projection_refresh(platform_name):
    """Check only the active format every 30 minutes to keep app startup responsive."""
    from datetime import datetime
    status = refresh_public_projection_sources((platform_name,))
    now = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %I:%M:%S %p %Z")
'''

new = '''@st.fragment(run_every="30m")
def automatic_projection_refresh(platform_name):
    """Check only the active format at most once every 30 minutes, even across full app reruns."""
    from datetime import datetime, timedelta
    now_dt = datetime.now(ZoneInfo("America/New_York"))
    throttle_key = "automatic_projection_last_check_" + str(platform_name).strip().casefold().replace(" ", "_")
    last_check = st.session_state.get(throttle_key)
    should_refresh = True
    if isinstance(last_check, datetime):
        should_refresh = (now_dt - last_check) >= timedelta(minutes=30)

    if should_refresh:
        status = refresh_public_projection_sources((platform_name,))
        st.session_state[throttle_key] = now_dt
        st.session_state["automatic_projection_last_status_" + str(platform_name)] = status
    else:
        status = st.session_state.get(
            "automatic_projection_last_status_" + str(platform_name), {}
        )

    effective_check = st.session_state.get(throttle_key, now_dt)
    now = effective_check.strftime("%Y-%m-%d %I:%M:%S %p %Z")
'''

if new in text:
    print("Automatic projection refresh throttle already applied.")
elif old in text:
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
    print("Throttled automatic projection refresh to one real check per 30 minutes.")
else:
    raise SystemExit("Could not find automatic projection refresh block")
