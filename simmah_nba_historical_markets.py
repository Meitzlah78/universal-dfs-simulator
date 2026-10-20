"""Provider-labeled archived closing NBA lines; not independently frozen snapshots."""
import json
from urllib.request import urlopen
from simmah_nba_history import BASE,parse_game
from simmah_nba_markets import implied_scores


def parse_closing_market(payload,event_id,before):
    game=parse_game(payload,event_id,before)
    competitors=payload['header']['competitions'][0]['competitors']
    teams={x['homeAway']:str(x['id']) for x in competitors}
    matches=[r for r in payload.get('pickcenter',[]) if str(r.get('provider',{}).get('id'))=='100']
    if len(matches)!=1:raise ValueError('Unique DraftKings historical odds record required')
    row=matches[0]
    # Explicit close fields only; never substitute current/default/open odds.
    home=float(row['pointSpread']['home']['close']['line'])
    away=float(row['pointSpread']['away']['close']['line'])
    over=str(row['total']['over']['close']['line'])
    under=str(row['total']['under']['close']['line'])
    if not over.startswith('o') or not under.startswith('u'):raise ValueError('Malformed closing total')
    total=float(over[1:])
    if abs(home+away)>1e-8 or abs(total-float(under[1:]))>1e-8:
        raise ValueError('Inconsistent two-sided historical lines')
    hp,ap=implied_scores(total,home)
    return {'event_id':str(event_id),'date':game['date'],'total':total,'home_spread':home,
            'team_implied_points':{teams['home']:hp,teams['away']:ap},
            'source':'ESPN / DraftKings provider-labeled closing lines',
            'provenance':'retrieved after game; closing label not independently timestamp-verified'}


def download_closing_market(event_id,before):
    if not str(event_id).isdigit():raise ValueError('Numeric NBA event ID required')
    with urlopen(BASE+'summary?event='+str(event_id),timeout=15) as response:
        return parse_closing_market(json.load(response),event_id,before)
