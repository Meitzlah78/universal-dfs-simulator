"""Freeze a pregame DraftEdge DvP challenger; never overwrite an existing trial."""
import concurrent.futures, hashlib, io, json, re, sys, urllib.request
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/dvp_trials/2026-10-19-was-sf'
KICKOFF = pd.Timestamp('2026-10-20T00:15:00Z')

def fetch(position):
    url = 'https://draftedge.com/nfl/nfl-defense-vs-pos/?pos=' + position.lower()
    raw = urllib.request.urlopen(url, timeout=30).read()
    table = pd.read_html(io.StringIO(raw.decode()))[0]
    if len(table) != 32 or not {'Team','DK FPA','FD FPA','Rank'} <= set(table):
        raise ValueError('Unexpected DvP table: ' + position)
    table['Defense'] = table.Team.str.extract(r'([A-Z]{2,3})$')[0].replace({'LA':'LAR'})
    if table.Defense.nunique() != 32:
        raise ValueError('Ambiguous defense keys')
    for col in ['DK FPA','FD FPA']:
        table[col] = pd.to_numeric(table[col], errors='raise')
        if not table[col].gt(0).all():
            raise ValueError('Invalid fantasy points allowed')
    table['Position'] = position
    return table, {'url':url,'sha256':hashlib.sha256(raw).hexdigest(),
        'fetched_at':datetime.now(timezone.utc).isoformat()}

def main():
    if pd.Timestamp.now(tz='UTC') >= KICKOFF:
        raise ValueError('Trial must be frozen before kickoff')
    if OUT.exists():
        raise FileExistsError('Refusing to replace a frozen trial')
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        fetched = list(executor.map(fetch, ['QB','RB','WR','TE']))
    table = pd.concat([t for t,meta in fetched], ignore_index=True)
    base = pd.read_csv(ROOT / 'data/market_trials/2026-10-19-was-sf/frozen-comparison.csv')
    rows = []
    for row in base.itertuples():
        opponent = {'SF':'WAS','WAS':'SF'}[row.Team]
        col = {'DraftKings':'DK FPA','FanDuel':'FD FPA'}[row.Platform]
        group = table[table.Position.eq(row.Position)]
        matched = group[group.Defense.eq(opponent)]
        ratio = float(matched.iloc[0][col] / group[col].mean()) if len(matched)==1 else 1.
        # Fixed exploratory strength, declared before outcomes; not fitted.
        factor = max(.9, min(1.1, 1 + .25*(ratio-1)))
        rows.append(dict(Platform=row.Platform,Name=row.Name,Team=row.Team,
            Opponent=opponent,Position=row.Position,Baseline=row.Baseline,
            DvPRatio=ratio,Factor=factor,Experimental=row.Baseline*factor,
            Change=row.Baseline*(factor-1),Matched=len(matched)==1))
    manifest = dict(kickoff=KICKOFF.isoformat(),created_at=datetime.now(timezone.utc).isoformat(),
        sources=[meta for t,meta in fetched],rule='baseline * clip(1 + 0.25*(opponent platform FPA / position league mean - 1), 0.9, 1.1)',
        scope='Prospective point-projection test only. No live app changes. No past-slate backtest: current rankings may contain those outcomes.',
        caveats=['DraftEdge blend weights are not fully specified; this uses posted tables, not a reconstruction.',
            'Possible double counting: source projections may already incorporate defensive matchups.',
            'FD baseline includes generic DraftEdge projections whose scoring basis is not independently verified.',
            'One game cannot establish predictive or ROI improvement. K and DST unchanged; DST requires verified actual scores.'])
    OUT.mkdir(parents=True)
    table.to_csv(OUT/'rankings.csv',index=False)
    pd.DataFrame(rows).to_csv(OUT/'frozen-comparison.csv',index=False)
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(pd.DataFrame(rows).query('Matched')[['Platform','Name','Baseline','Experimental','Change']].to_string(index=False))

if __name__ == '__main__':
    main()
