"""Site-independent NBA lineup confirmation from the dated public lineup page."""
from html.parser import HTMLParser
import time
from urllib.request import urlopen
from simmah_nba_projections import team_key,player_key
from simmah_nba_game_strip import explicit_true


class LineupPage(HTMLParser):
    def __init__(self):
        super().__init__();self.day=None;self.cards=[];self.card=None;self.depth=0;self.list=None;self.abbr=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs);classes=set(a.get('class','').split())
        if a.get('data-gamedate'):self.day=a['data-gamedate']
        if self.card is None:
            if tag=='div' and 'lineup' in classes and a.get('data-lnum'):
                self.card={'teams':[],'lists':[]};self.depth=1
            return
        if tag=='div':
            self.depth+=1
            if 'lineup__abbr' in classes:self.abbr=self.depth
        if tag=='ul' and 'lineup__list' in classes:
            side='away' if 'is-visit' in classes else 'home' if 'is-home' in classes else None
            self.list={'side':side,'confirmed':False,'names':[]}
            self.card['lists'].append(self.list)
        if self.list is not None:
            if tag=='li' and 'lineup__status' in classes:self.list['confirmed']='is-confirmed' in classes
            if tag=='a' and '/basketball/player/' in a.get('href','') and len(self.list['names'])<5:
                name=a.get('title','').strip()
                if name:self.list['names'].append(name)
    def handle_data(self,data):
        if self.card is not None and self.abbr is not None and data.strip():self.card['teams'].append(team_key(data.strip()))
    def handle_endtag(self,tag):
        if self.card is None:return
        if tag=='ul':self.list=None
        if tag=='div':
            if self.abbr==self.depth:self.abbr=None
            self.depth-=1
            if self.depth==0:
                self.cards.append(self.card);self.card=None;self.list=None


def parse_confirmed_page(html,day,pairs):
    parser=LineupPage();parser.feed(html)
    if parser.day!=day:raise ValueError('NBA lineup page date does not match slate')
    expected={tuple(sorted(map(team_key,p))) for p in pairs};seen=set();values={}
    for card in parser.cards:
        teams=card['teams']
        if len(teams)!=2 or teams[0]==teams[1]:continue
        pair=tuple(sorted(teams))
        if pair not in expected:continue
        if pair in seen:raise ValueError('Duplicate lineup-page matchup')
        seen.add(pair)
        sides={item['side']:item for item in card['lists'] if item['side'] is not None}
        for team,side in zip(teams,('away','home')):
            detail=sides.get(side)
            if detail is None:continue
            names=detail['names'];keys=[player_key(name,team) for name in names]
            if len(keys)!=5 or len(set(keys))!=5:continue
            for key in keys:values[key]={'Expected Starter':True,'Starter Confirmed':detail['confirmed']}
    if not values:raise ValueError('No complete NBA starting five supplied for this slate')
    return values


def download_lineup_page(day):
    from datetime import date
    date.fromisoformat(day)
    with urlopen('https://www.rotowire.com/basketball/nba-lineups.php?date='+day,timeout=3) as response:
        html=response.read().decode('utf-8')
    return {'html':html,'checked_at':time.time()}


def cached_confirmed_status(st,day,pairs):
    # Cache by day, not site/slate or game subset: DK and FD must read the
    # same page snapshot even when one slate contains additional games.
    page=st.cache_data(ttl=60,show_spinner=False,max_entries=8)(download_lineup_page_result)(day)
    if page.get('error'):raise ValueError(page['error'])
    return {'players':parse_confirmed_page(page['html'],day,pairs),
            'checked_at':page['checked_at'],'source':'RotoWire shared NBA lineup page'}


def download_lineup_page_result(day):
    try:return download_lineup_page(day)
    except (ValueError,OSError,KeyError,TypeError) as exc:
        return {'error':str(exc),'checked_at':time.time()}


def current_confirmed_pool(st,pool,day,pairs):
    scope=(day,tuple(sorted({tuple(sorted(map(team_key,p))) for p in pairs})))
    saved=st.session_state.get('nba_confirmed_last_good',{})
    stale=False
    try:
        response=cached_confirmed_status(st,day,pairs)
        st.session_state['nba_confirmed_last_good']={'scope':scope,'response':response}
    except (ValueError,OSError,KeyError,TypeError):
        stale=True
        response=saved.get('response',{}) if saved.get('scope')==scope else {}
        if not response and pool.attrs.get('slate_date')!=day:
            pool=pool.copy()
            pool['Expected Starter']=False
            pool['Starter Confirmed']=False
    view=apply_confirmed_status(pool,response.get('players',{}))
    if stale:view['Lineup Status Stale']=True
    return view,{**response,'stale':stale}


def apply_confirmed_status(pool,values):
    view=pool.copy()
    view['Expected Starter']=False;view['Starter Confirmed']=False
    view['Lineup Status Stale']=False
    source_teams={team_key(key[1]) for key in values}
    for index,row in view.iterrows():
        detail=values.get(player_key(row['Name'],row['Team']),{})
        missing_team=team_key(row['Team']) not in source_teams
        fallback=pool.at[index,'Expected Starter'] if missing_team and 'Expected Starter' in pool else False
        view.at[index,'Expected Starter']=explicit_true(detail.get('Expected Starter',fallback))
        view.at[index,'Starter Confirmed']=explicit_true(detail.get('Starter Confirmed',False))
        view.at[index,'Lineup Status Stale']=missing_team
    return view

