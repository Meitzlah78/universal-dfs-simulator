from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")
old = '''        valid = np.flatnonzero((salary_batch <= salary_cap) & (salary_batch >= 49000) & multi_team)\n'''
new = '''        # Match completed DK Showdown salary behavior instead of hard-cutting at $49K.\n        # BUF@LAR: mean $49,459; P5 $48,200; P10 $48,700; P25 $49,300;\n        # median $49,700; P75 $49,900; P90/P95 $50,000. Keep a small real\n        # low-salary tail while strongly favoring near-cap public constructions.\n        salary_left = salary_cap - salary_batch\n        salary_acceptance = np.select(\n            [\n                salary_left <= 100,\n                salary_left <= 300,\n                salary_left <= 700,\n                salary_left <= 1300,\n                salary_left <= 1800,\n            ],\n            [1.00, 0.92, 0.72, 0.42, 0.20],\n            default=0.06,\n        )\n        salary_draw = rng.random(n)\n        valid = np.flatnonzero(\n            (salary_batch <= salary_cap)\n            & (salary_batch >= 45000)\n            & multi_team\n            & (salary_draw <= salary_acceptance)\n        )\n'''
if new in text:
    print("DK Showdown salary profile already installed.")
elif old in text:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("Installed real-field DK Showdown salary profile.")
else:
    raise SystemExit("Could not find hard $49K DK Showdown salary filter")
