from pathlib import Path

p = Path("dfs_app.py")
s = p.read_text(encoding="utf-8")

old = '''                response = requests.get(
                    f"https://api.fantasypros.com/public/v2/json/nfl/{season}/projections",
                    headers={"x-api-key": api_key, "Accept": "application/json"},
                    params=params,
                    timeout=(5, 30),
                )
                response.raise_for_status()
                payload = response.json()
'''
new = '''                projection_url = f"https://api.fantasypros.com/public/v2/json/nfl/{season}/projections"
                response = requests.get(
                    projection_url,
                    headers={"x-api-key": api_key, "Accept": "application/json"},
                    params=params,
                    timeout=(5, 30),
                )
                if response.status_code == 429:
                    # Do not hammer FantasyPros when its quota is exhausted. A
                    # refresh can still continue with DFF/DraftEdge; Streamlit's
                    # 15-minute cache prevents successful responses being fetched
                    # again on every rerun.
                    retry_after = str(response.headers.get("Retry-After", "")).strip()
                    wait_note = f" Retry after {retry_after}s." if retry_after else ""
                    st.info(f"FantasyPros rate limit reached; using DFF/DraftEdge for this refresh.{wait_note}")
                    return result
                response.raise_for_status()
                payload = response.json()
'''
if old not in s:
    if 'FantasyPros rate limit reached; using DFF/DraftEdge' in s:
        print("FantasyPros rate-limit handling already applied")
        raise SystemExit(0)
    raise SystemExit("FantasyPros request block not found")
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("FantasyPros rate-limit handling applied")
