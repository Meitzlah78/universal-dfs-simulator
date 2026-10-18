"""Preserve distinct snapshot contents without multiplying files on UI reruns."""
import hashlib
import json
from datetime import datetime, timezone


def archive_snapshot(folder, snapshot, metadata, format_slug, slate_id):
    folder = folder / 'archive' / format_slug / slate_id
    folder.mkdir(parents=True, exist_ok=True)
    stable_frame = snapshot.drop(columns=['Snapshot Saved ET'], errors='ignore')
    stable_meta = {k: v for k, v in metadata.items() if k not in {'saved_at_et', 'archive_path'}}
    digest = hashlib.sha256((stable_frame.to_csv(index=False) + json.dumps(stable_meta, sort_keys=True)).encode()).hexdigest()
    existing = sorted(folder.glob(f'*_{digest}.csv'))
    if existing:
        return existing[0]
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    path = folder / f'{stamp}_{digest}.csv'
    # A timestamped version is independent of the compatibility latest files.
    path.write_text(snapshot.to_csv(index=False), encoding='utf-8')
    path.with_suffix('.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    return path
