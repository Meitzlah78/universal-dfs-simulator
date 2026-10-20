"""NBA slate scores and conservative, source-backed starting-lineup status."""
from datetime import datetime
from html import escape
import math
from zoneinfo import ZoneInfo
from simmah_nba_projections import team_key


def explicit_true(value):
    return str(value).strip().casefold() in {'true','yes','1'}


def team_lineup(pool,team):
    rows=pool[pool['Team'].map(team_key)==team_key(team)]
    if 'Expected Starter' not in rows or 'Starter Confirmed' not in rows:
        return {'status':'Unavailable','starters':[]}
    starters=rows[rows['Expected Starter'].map(explicit_true)]
    names=starters['Name'].astype(str).tolist()
    if len(starters)!=5:
        return {'status':'Pending' if len(starters) else 'Unavailable','starters':names}
    injured=starters['Injury Status'].astype(str).str.upper().isin({'O','OUT','IR','SUSPENDED'}).any()
    confirmed=starters['Starter Confirmed'].map(explicit_true).all()
    return {'status':'Confirmed' if confirmed and not injured else 'Expected', 'starters':names}


def game_records(pool,markets):
    pairs={tuple(sorted((team_key(r.Team),team_key(r.Opponent)))) for r in pool.itertuples()}
    lines={tuple(sorted(map(team_key,m['teams']))):m for m in markets}
    records=[]
    for pair in sorted(pairs):
        order=pair;separator=' vs '
        if 'Game' in pool:
            for game in pool['Game'].dropna().astype(str).unique():
                parts=tuple(team_key(x) for x in game.split('@'))
                if len(parts)==2 and set(parts)==set(pair):
                    order=parts;separator=' @ ';break
        market=lines.get(pair)
        scores={} if market is None else dict(zip(map(team_key,market['teams']),market['implied_points']))
        teams=[]
        for team in order:
            score=scores.get(team)
            try:score=float(score);score=score if math.isfinite(score) and score>0 else None
            except (TypeError,ValueError):score=None
            teams.append({'team':team,'score':score,**team_lineup(pool,team)})
        records.append({'label':separator.join(order),'teams':teams})
    return records


def render_game_strip(st,pool,markets,updated_at=None):
    games=game_records(pool,markets)
    if not games:return
    colors={'Confirmed':'#69db9b','Expected':'#ffd166','Pending':'#ffd166','Unavailable':'#a3adba'}
    symbols={'Confirmed':'●','Expected':'○','Pending':'○','Unavailable':'—'}
    cards=[]
    for game in games:
        teams=[]
        for t in game['teams']:
            score='—' if t['score'] is None else f"{t['score']:.1f}"
            status=t['status'];tooltip=', '.join(t['starters']) or 'No complete starting five supplied by source'
            teams.append(f'<div class="simmah-game-team"><strong>{escape(t["team"])}</strong><strong>{score}</strong>'
                         f'<span title="{escape(tooltip,quote=True)}" style="color:{colors[status]}">{symbols[status]} {status}</span></div>')
        cards.append('<div class="simmah-game-card"><div class="simmah-game-title">'+escape(game['label'])+'</div>'+''.join(teams)+'</div>')
    st.markdown('''<style>
.simmah-game-strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin:4px 0 10px}
.simmah-game-card{padding:10px 13px;border:1px solid #45515f;border-radius:9px;background:rgba(100,115,135,.08)}
.simmah-game-title{font-size:.75rem;opacity:.7;margin-bottom:6px}
.simmah-game-team{display:grid;grid-template-columns:42px 56px 1fr;align-items:center;gap:9px;padding:2px 0}
.simmah-game-team span{font-size:.78rem;white-space:nowrap}
</style><div class="simmah-game-strip">'''+''.join(cards)+'</div>',unsafe_allow_html=True)
    stamp=''
    if updated_at is not None:
        stamp=' · checked '+datetime.fromtimestamp(updated_at,ZoneInfo('America/New_York')).strftime('%I:%M %p ET').lstrip('0')
    st.caption('Scores: market-implied team points. Lineups: [RotoWire](https://www.rotowire.com/basketball/nba-lineups.php); Confirmed requires five explicitly confirmed starters.'+stamp)
