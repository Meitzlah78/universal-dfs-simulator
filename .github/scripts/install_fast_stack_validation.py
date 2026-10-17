from pathlib import Path

APP = Path("dfs_app.py")
text = APP.read_text(encoding="utf-8")


def replace_once(old, new, label):
    global text
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"Patch anchor not found: {label}")
    text = text.replace(old, new, 1)


replace_once(
'''def full_roster_stack_matches(chosen, pool, selected_stacks):
    """Return True when a full-roster lineup matches at least one selected QB stack rule."""
''',
'''def full_roster_stack_matches(chosen, pool, selected_stacks, stack_lookup=None):
    """Return True when a full-roster lineup matches at least one selected QB stack rule."""
''',
"stack helper signature",
)

replace_once(
'''    lookup = pool.drop_duplicates("Name", keep="first").set_index("Name")
''',
'''    lookup = stack_lookup
    if lookup is None:
        lookup = pool.drop_duplicates("Name", keep="first").set_index("Name")
''',
"stack lookup fallback",
)

# The optional stack_lookup parameter allows each builder to precompute the
# Name-indexed metadata table once and reuse it for every candidate. Existing
# three-argument call sites remain valid, so this is backward compatible.
APP.write_text(text, encoding="utf-8")
print("Installed reusable full-roster stack lookup support")
