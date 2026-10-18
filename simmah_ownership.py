"""Experimental public DK Classic ownership; never substitutes point projections."""
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
import unicodedata

URL = 'https://desk.sharksnip.com/picks/dfs/nfl'


def _team(value):
    value = str(value).strip().upper()
    return {'LA': 'LAR', 'JAC': 'JAX', 'WSH': 'WAS'}.get(value, value)


def _key(value):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode().lower())


class _Table(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.cell = None
        self.row = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag == 'table' and dict(attrs).get('data-testid') == 'picks-dfs-table':
            self.active = True
        if self.active and tag in ('td', 'th'):
            self.cell = ''
        if self.active and tag == 'tr':
            self.row = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data

    def handle_endtag(self, tag):
        if self.active and tag in ('td', 'th') and self.cell is not None:
            self.row.append(self.cell.strip())
            self.cell = None
        if self.active and tag == 'tr':
            self.rows.append(self.row)
        if tag == 'table':
            self.active = False


def parse_sharksnip(html, now=None):
    now = now or datetime.now(timezone.utc)
    if 'DraftKings classic' not in html:
        raise ValueError('Source is not DraftKings Classic')
    def required(pattern):
        match = re.search(pattern, html)
        if not match:
            raise ValueError('Missing ownership slate metadata')
        return match.group(1)
    generated = datetime.fromisoformat(required(r'generatedAt:"([^"]+)"').replace('Z', '+00:00'))
    starts = datetime.fromisoformat(required(r'startsAt:"([^"]+)"').replace('Z', '+00:00'))
    if not -300 <= (now-generated).total_seconds() <= 86400 or now >= starts:
        raise ValueError('Ownership source is stale or slate has started')
    group = required(r'draftGroupId:"(\d+)"')
    games_raw = required(r'gameIds:\[([^\]]+)\]')
    games = set()
    for game in re.findall(r'"([^"]+)"', games_raw):
        bits = game.split('_')
        if len(bits) != 4:
            raise ValueError('Invalid ownership game metadata')
        games.add(tuple(sorted((_team(bits[2]), _team(bits[3])))))
    parser = _Table()
    parser.feed(html)
    expected = ['Player','Pos','Team','Opp','DK Salary','Proj','Value (pts/$1K)','Own% (modelled)']
    if not parser.rows or parser.rows[0] != expected or not games:
        raise ValueError('Ownership table schema changed')
    rows = {}
    for row in parser.rows[1:]:
        if len(row) != 8 or not row[7].endswith('%'):
            continue
        try:
            own = float(row[7][:-1])
            salary = int(row[4].replace('$','').replace(',',''))
        except ValueError:
            continue
        if not 0 <= own <= 100:
            continue
        key = (_key(row[0]), _team(row[2]), _team(row[3]), row[1].upper(), salary)
        if key in rows:
            raise ValueError('Ambiguous ownership player row')
        rows[key] = own
    if not rows:
        raise ValueError('No valid ownership values')
    return rows, {'source': 'SharkSnip experimental', 'generated_at': generated.isoformat(),
                  'draft_group': group, 'games': games}


def apply_sharksnip(pool, html, now=None):
    import pandas as pd
    result = pool.copy()
    # A supplied ownership column always wins, including its zero values.
    aliases = {'projected ownership','projected own %','ownership %','ownership','projected own','own%','own'}
    if any(str(c).strip().lower() in aliases for c in result.columns):
        return result, 'Uploaded ownership retained; automatic ownership skipped.'
    rows, meta = parse_sharksnip(html, now)
    games = {tuple(sorted((_team(r.Team), _team(r.Opponent)))) for r in result.itertuples()}
    if games != meta['games']:
        raise ValueError('Ownership slate games do not match the uploaded player pool')
    values = []
    for r in result.itertuples():
        pos = 'DST' if str(r.Position).upper() in {'D','DEF','DST'} else str(r.Position).upper()
        values.append(rows.get((_key(r.Name), _team(r.Team), _team(r.Opponent), pos, int(r.Salary))))
    matched = sum(v is not None for v in values)
    if matched < .9 * len(result):
        raise ValueError(f'Ownership coverage too low: {matched}/{len(result)} matched')
    # Missing rows keep the same projection-rank fallback, scaled to matched values.
    own = pd.Series(values, index=result.index, dtype=float)
    proxy = .1 + pd.to_numeric(result['MeanPoints'], errors='coerce').rank(pct=True)**2
    scale = float((own[own.notna()] / proxy[own.notna()]).median())
    combined = own.fillna(proxy * scale).clip(0,100)
    # Nine roster spots impose hard limits on marginal ownership totals.
    # Reject the whole feed rather than amplify malformed popularity values.
    positions = result['Position'].astype(str).str.upper().replace({'D':'DST','DEF':'DST'})
    limits = {'QB':125, 'DST':125, 'RB':330, 'WR':440, 'TE':220}
    if combined.sum() > 990 or any(float(combined[positions == pos].sum()) > limit for pos, limit in limits.items()):
        raise ValueError('Ownership totals exceed legal roster capacity; source rejected')
    result['Projected Ownership'] = combined
    result['Ownership Source'] = ['SharkSnip experimental' if v is not None else 'Projection-rank fallback' for v in values]
    result['Ownership Updated UTC'] = meta['generated_at']
    result['Ownership Draft Group'] = meta['draft_group']
    return result, f"Experimental SharkSnip DK Classic ownership: {matched}/{len(result)} matched; {len(result)-matched} use estimated popularity. Source updated {meta['generated_at']}; draft group {meta['draft_group']}. Ownership accuracy is unvalidated."
