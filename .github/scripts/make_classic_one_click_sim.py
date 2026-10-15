from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text(encoding='utf-8')

# Hotfix contests do not store a separate `pays` key. The last paid place is
# already present in each exact payout ladder, so derive it from that ladder.
text = text.replace(
    'float(classic_contest["pays"]) / float(full_field_size)',
    'float(max(last for _, last, _ in classic_contest["payouts"])) / float(full_field_size)'
)

path.write_text(text, encoding='utf-8')
print('Fixed Classic payout cutoff by deriving paid places from payout ladder.')
