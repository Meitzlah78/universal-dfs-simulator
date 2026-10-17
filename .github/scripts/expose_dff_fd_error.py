from pathlib import Path
p=Path('dfs_app.py')
s=p.read_text()
old='''        except Exception:\n            pass\n\n    if source_name == "DFF":\n'''
new='''        except Exception as exc:\n            # Surface the real Streamlit-runtime failure instead of silently\n            # converting it into an unavailable projection source.\n            st.error(f"DFF FanDuel Single Game loader error: {type(exc).__name__}: {exc}")\n\n    if source_name == "DFF":\n'''
if old not in s:
    raise SystemExit('diagnostic insertion point not found')
s=s.replace(old,new,1)
p.write_text(s)
print('DFF runtime diagnostic installed')
