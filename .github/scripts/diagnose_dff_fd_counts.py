from pathlib import Path
p=Path('dfs_app.py')
s=p.read_text()
old='''            # API order is newest first in current DFF responses; preserve it.\n            for slate_date in recent_dates:\n'''
new='''            dff_debug = []\n            for slate_date in recent_dates:\n'''
s=s.replace(old,new,1)
old2='''                    overlap = target_keys.intersection(values)\n                    if len(overlap) >= min(2, len(target_keys)):\n                        return values\n        except Exception as exc:\n'''
new2='''                    overlap = target_keys.intersection(values)\n                    dff_debug.append(f"{slate_date}: rows={len(values)}, overlap={len(overlap)}")\n                    if len(overlap) >= min(2, len(target_keys)):\n                        return values\n            st.warning("DFF FanDuel diagnostic — " + ("; ".join(dff_debug) if dff_debug else f"dates={recent_dates!r}; no projection table parsed"))\n        except Exception as exc:\n'''
if old2 not in s:
    raise SystemExit('second insertion point not found')
s=s.replace(old2,new2,1)
p.write_text(s)
print('DFF count diagnostics installed')
