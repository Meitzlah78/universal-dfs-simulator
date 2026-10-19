"""Stable candidate identity, independent of portfolio controls and live projections."""
import hashlib


def uploaded_slate_signature(uploaded_file, platform, mode):
    # getvalue leaves the upload cursor untouched and detects a genuinely new file.
    return (platform, mode, hashlib.sha256(uploaded_file.getvalue()).hexdigest())


def signature_matches_upload(previous, current, eligible_rows):
    """Migrate the old FD row signature only when its salary roster still matches."""
    if previous == current:
        return True
    if not isinstance(previous, tuple) or len(previous) != 3 or previous[:2] != current[:2]:
        return False
    rows = previous[2]
    if not isinstance(rows, tuple):
        return False
    return {tuple(map(str, row[:4])) for row in rows if isinstance(row, tuple) and len(row) >= 4} == {tuple(map(str, row)) for row in eligible_rows}
