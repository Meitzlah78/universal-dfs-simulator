"""Compact NFL game cards; presentation only, no changes to market inputs."""
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo


def game_cards_html(games):
    cards=[]
    for game in games:
        away=escape(str(game['away']));home=escape(str(game['home']))
        points=game.get('points')
        score='Lines pending' if points is None else f'{away} {points[0]:g} · {home} {points[1]:g}'
        kickoff=game.get('kickoff');time=''
        if kickoff:
            try:time=datetime.fromisoformat(str(kickoff).replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York')).strftime('%I:%M %p ET').lstrip('0')
            except (ValueError,TypeError):pass
        details=''
        if points is not None:details=f"Total {float(game['total']):g} · {home} {float(game['spread']):+g}"
        cards.append(f'<div class="simmah-nfl-card" title="{escape(str(game.get("source","")),quote=True)}"><b>{away} @ {home}</b><span>{score}</span><small>{time} {details}</small></div>')
    return '<div class="simmah-nfl-games" aria-label="NFL slate games">'+''.join(cards)+'</div>'


def render_game_cards(st,games):
    st.markdown('''<style>
.simmah-nfl-games{display:flex;gap:8px;overflow-x:auto;padding:4px 2px 9px;scrollbar-width:thin}
.simmah-nfl-card{flex:0 0 190px;padding:9px 11px;border:1px solid #28455d;border-radius:8px;background:#0b1b2b;color:#e8f1f8}
.simmah-nfl-card b,.simmah-nfl-card span,.simmah-nfl-card small{display:block;white-space:nowrap}
.simmah-nfl-card b{font-size:12px}.simmah-nfl-card span{font-size:13px;margin:4px 0}.simmah-nfl-card small{font-size:10px;color:#a8bbcc}
.st-key-simmah_pinned_games:has(.simmah-nfl-games){position:sticky;top:9.5rem;z-index:978;background:#061321;max-width:77%}
@media(max-width:900px){.st-key-simmah_pinned_games:has(.simmah-nfl-games){max-width:100%}}
</style>'''+game_cards_html(games),unsafe_allow_html=True)
