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
.simmah-nfl-games{display:flex;gap:8px;overflow-x:auto;padding:4px 2px 9px;scrollbar-width:thin}
.simmah-nfl-card{flex:0 0 190px;padding:9px 11px;border:1px solid #28455d;border-radius:8px;background:#0b1b2b;color:#e8f1f8}
.simmah-nfl-card strong,.simmah-nfl-card b,.simmah-nfl-card span,.simmah-nfl-card small{display:block;white-space:nowrap}
.simmah-nfl-kickoff{font-size:12px;color:#8dd5ff;margin-bottom:4px}.simmah-nfl-card b{font-size:12px}.simmah-nfl-card span{font-size:13px;margin:4px 0}.simmah-nfl-card small{font-size:10px;color:#a8bbcc}
.st-key-simmah_pinned_games:has(.simmah-nfl-games){position:fixed !important;top:7rem;left:50%;transform:translateX(-50%);width:calc(100% - 3rem) !important;max-width:1752px;max-height:8.5rem;overflow-y:auto;z-index:989;background:#061321;padding:4px 0;border-bottom:1px solid #293e52;box-shadow:0 4px 12px #0003;min-width:0}
.stApp:has(.simmah-nfl-games) [data-testid="stTabs"] :is([data-baseweb="tab-list"], [role="tablist"]){top:16rem !important;z-index:988}
.stApp:has(.simmah-nfl-games) [data-testid="stMainBlockContainer"],.stApp:has(.simmah-nfl-games) section.main>div.block-container{padding-top:19.5rem !important}
@media(min-width:901px){.stApp:has(.simmah-nfl-games) .st-key-simmah_build_panel{top:19rem !important;height:max(8rem,calc(100dvh - 20rem)) !important}}
@media(max-width:640px){.st-key-simmah_pinned_games:has(.simmah-nfl-games){width:calc(100% - 1rem) !important}}

/* Stack fixed bars against their actual rendered edges, including mobile. */
.st-key-simmah_pinned_games:has(.simmah-nfl-games){anchor-name:--simmah-games;margin:0 !important;border-top:0;border-radius:0}
@supports(top:anchor(--simmah-refresh bottom)){
 .st-key-simmah_pinned_games:has(.simmah-nfl-games){top:anchor(--simmah-refresh bottom) !important}
 .stApp:has(.simmah-nfl-games) [data-testid="stTabs"] :is([data-baseweb="tab-list"], [role="tablist"]){top:anchor(--simmah-games bottom) !important;margin-top:0 !important;border-top:0}
}
</style>'''+game_cards_html(games),unsafe_allow_html=True)
