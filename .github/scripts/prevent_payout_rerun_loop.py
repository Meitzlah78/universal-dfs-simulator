from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")
old = '''                st.rerun()\n            except Exception as exc:\n'''
new = '''                # Continue into contest scoring on the same run. Restarting the\n                # Streamlit script here can trap the app in a fetch/rerun loop when\n                # DraftKings returns contest details without a complete payout table.\n            except Exception as exc:\n'''
if old not in text:
    if new in text:
        print("Payout rerun loop guard already applied.")
    else:
        raise SystemExit("Could not find the contest-details rerun block")
else:
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
    print("Removed contest-details rerun so Step 4 can start.")
