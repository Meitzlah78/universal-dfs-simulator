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


def start_time_label(values):
    starts=set()
    for value in values:
        try:
            if ':' not in str(value):continue
            instant=datetime.fromisoformat(str(value).replace('Z','+00:00'))
            # RotoWire's naive game.dateTime values are Eastern local times.
            if instant.tzinfo is None:instant=instant.replace(tzinfo=ZoneInfo('America/New_York'))
            starts.add(instant.astimezone(ZoneInfo('America/New_York')))
        except (ValueError,TypeError):continue
    if len(starts)!=1:return 'Time TBD'
    return next(iter(starts)).strftime('%I:%M %p ET').lstrip('0')


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
        rows=pool[pool['Team'].map(team_key).isin(pair)]
        start=start_time_label(rows['Game Start'].dropna()) if 'Game Start' in rows else 'Time TBD'
        records.append({'label':separator.join(order),'start_time':start,'teams':teams})
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
        cards.append('<div class="simmah-game-card"><div class="simmah-game-title">'+escape(game['label'])+'<span>'+escape(game['start_time'])+'</span></div>'+''.join(teams)+'</div>')
    st.markdown('''<style>
.st-key-simmah_pinned_games{position:sticky;top:3.75rem;z-index:100;background:var(--background-color,#0e1117);padding:4px 0;border-bottom:1px solid #293e52;box-shadow:0 4px 12px #0003;min-width:0}
.simmah-game-strip{display:flex;flex-wrap:nowrap;gap:7px;overflow-x:scroll;overflow-y:hidden;width:100%;max-width:100%;min-width:0;box-sizing:border-box;padding:7px 7px 9px;margin:2px 0 7px;border:1px solid #293e52;border-radius:8px;scroll-snap-type:x proximity;scrollbar-width:auto;scrollbar-gutter:stable;scrollbar-color:#50728f #102337;-webkit-overflow-scrolling:touch}
.simmah-game-strip::after{content:"";flex:0 0 18px}
.simmah-game-strip::-webkit-scrollbar{height:12px}
.simmah-game-strip::-webkit-scrollbar-track{background:#102337;border-radius:6px}
.simmah-game-strip::-webkit-scrollbar-thumb{background:#6f8da8;border:2px solid #102337;border-radius:6px}
.simmah-game-card{flex:0 0 205px;box-sizing:border-box;scroll-snap-align:start;padding:6px 9px;border:1px solid #45515f;border-radius:6px;background:rgba(100,115,135,.08)}
.simmah-game-title{display:flex;justify-content:space-between;gap:8px;font-size:.65rem;opacity:.75;margin-bottom:3px;white-space:nowrap}
.simmah-game-team{display:grid;grid-template-columns:32px 43px 1fr;align-items:center;gap:5px;padding:1px 0;font-size:.78rem;line-height:1.25}
.simmah-game-team span{font-size:.67rem;white-space:nowrap}
.simmah-game-strip:focus-visible{outline:2px solid #69bce5;outline-offset:2px}
@media(max-width:440px){.simmah-game-card{flex-basis:195px}}
</style><div class="simmah-game-strip" role="region" aria-label="Slate games; scroll left or right" tabindex="0">'''+''.join(cards)+'</div>',unsafe_allow_html=True)
    stamp=''
    if updated_at is not None:
        stamp=' · checked '+datetime.fromtimestamp(updated_at,ZoneInfo('America/New_York')).strftime('%I:%M %p ET').lstrip('0')
    st.caption(f'{len(games)} games · Scroll horizontally below the cards to see every game. Scores: market-implied team points. Lineups: [RotoWire](https://www.rotowire.com/basketball/nba-lineups.php); Confirmed requires five explicitly confirmed starters.'+stamp)

