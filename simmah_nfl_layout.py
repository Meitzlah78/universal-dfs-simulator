"""Compact NFL game cards; presentation only, no changes to market inputs."""
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo


def kickoff_time(value):
    """Normalize verified kickoff values to Eastern; missing times sort last."""
    if value is None or not str(value).strip():
        return None
    try:
        instant = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=ZoneInfo('America/New_York'))
        return instant.astimezone(ZoneInfo('America/New_York'))
    except (ValueError, TypeError):
        return None


def game_cards_html(games):
    cards=[]
    ordered = sorted(games, key=lambda game: (
        kickoff_time(game.get('kickoff')).timestamp() if kickoff_time(game.get('kickoff')) else float('inf'),
        str(game['away']), str(game['home'])))
    for game in ordered:
        away=escape(str(game['away']));home=escape(str(game['home']))
        points=game.get('points')
        score='Lines pending' if points is None else f'{away} {points[0]:g} · {home} {points[1]:g}'
        kickoff=kickoff_time(game.get('kickoff'))
        time=kickoff.strftime('%I:%M %p ET').lstrip('0') if kickoff else 'Time TBD'
        details=''
        if points is not None:details=f"Total {float(game['total']):g} · {home} {float(game['spread']):+g}"
        cards.append(f'<div class="simmah-nfl-card" title="{escape(str(game.get("source","")),quote=True)}"><strong class="simmah-nfl-kickoff">{time}</strong><b>{away} @ {home}</b><span>{score}</span><small>{details}</small></div>')
    return '<div class="simmah-nfl-games" aria-label="NFL slate games">'+''.join(cards)+'</div>'


def render_game_cards(st,games):
    st.markdown('''<style>
.simmah-nfl-games{display:flex;gap:8px;overflow-x:auto;padding:3px 0 10px;scrollbar-width:thin}
.simmah-nfl-card{flex:0 0 172px;padding:10px 12px;border:1px solid #263b4d;border-radius:9px;background:#101d2b;color:#e6edf5}
.simmah-nfl-card strong,.simmah-nfl-card b,.simmah-nfl-card span,.simmah-nfl-card small{display:block;white-space:nowrap}
.simmah-nfl-kickoff{font-size:11px;color:#6cddcc;margin-bottom:5px}.simmah-nfl-card b{font-size:13px}.simmah-nfl-card span{font-size:12px;margin:4px 0}.simmah-nfl-card small{font-size:10px;color:#91a9bd}
.st-key-simmah_pinned_games:has(.simmah-nfl-games){position:relative;min-width:0;margin:.1rem 0 .65rem}
@media(max-width:640px){.simmah-nfl-card{flex-basis:145px;padding:8px 10px}}
</style>'''+game_cards_html(games),unsafe_allow_html=True)
