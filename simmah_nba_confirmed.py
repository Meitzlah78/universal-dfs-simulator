"""Site-independent NBA lineup confirmation from the dated public lineup page."""
from html.parser import HTMLParser
import time
from urllib.request import Request,urlopen
from simmah_nba_lineup_cache import LineupPageCache
from simmah_nba_projections import team_key,player_key
from simmah_nba_game_strip import explicit_true


class LineupPage(HTMLParser):
    def __init__(self):
        super().__init__();self.day=None;self.cards=[];self.card=None;self.depth=0;self.list=None;self.abbr=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs);classes=set(a.get('class','').split())
        if a.get('data-gamedate'):self.day=a['data-gamedate']
        if self.card is None:
            if tag=='div' and 'lineup' in classes and (a.get('data-lnum') or a.get('data-gameid') or 'is-nba' in classes):
                self.card={'teams':[],'lists':[]};self.depth=1
            return
        if tag=='div':
            self.depth+=1
        if 'lineup__abbr' in classes:self.abbr=(tag,self.depth)
        if tag=='ul' and 'lineup__list' in classes:
            side='away' if 'is-visit' in classes else 'home' if 'is-home' in classes else None
            self.list={'side':side,'confirmed':False,'names':[]}
            self.card['lists'].append(self.list)
        if self.list is not None:
            if tag=='li' and 'lineup__status' in classes:self.list['confirmed']='is-confirmed' in classes
            if tag=='a' and '/basketball/player' in a.get('href','') and len(self.list['names'])<5:
                name=a.get('title','').strip()
                if name:self.list['names'].append(name)
                else:self.name_parts=[]
    def handle_data(self,data):
        if self.card is not None and self.abbr is not None and data.strip():self.card['teams'].append(team_key(data.strip()))
        if self.card is not None and getattr(self,'name_parts',None) is not None:self.name_parts.append(data)
    def handle_endtag(self,tag):
        if self.card is None:return
        if tag=='a' and getattr(self,'name_parts',None) is not None:
            name=' '.join(''.join(self.name_parts).split());self.name_parts=None
            if name and self.list is not None and len(self.list['names'])<5:self.list['names'].append(name)
        if tag=='ul':self.list=None
        if self.abbr==(tag,self.depth):self.abbr=None
        if tag=='div':
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
    request=Request('https://www.rotowire.com/basketball/nba-lineups.php?date='+day,
                    headers={'User-Agent':'Mozilla/5.0','Accept':'text/html'})
    # Retry a transient read/connect timeout once in the background worker.
    # HTTP errors (including 403) are not retried or bypassed.
    from urllib.error import URLError
    for attempt in range(2):
        try:
            with urlopen(request,timeout=8) as response:
                html=response.read().decode('utf-8')
            return {'html':html,'checked_at':time.time()}
        except (TimeoutError,URLError) as exc:
            timed_out=isinstance(exc,TimeoutError) or isinstance(getattr(exc,'reason',None),TimeoutError)
            if not timed_out or attempt:raise


def cached_confirmed_status(st,day,pairs):
    # Cache by day, not site/slate or game subset: DK and FD must read the
    # same page snapshot even when one slate contains additional games.
    page=_lineup_cache.get(day)
    if not page.get('html') and page.get('pending'):raise LineupFetchPending('Checking the dated RotoWire lineup page')
    if page.get('error'):raise ValueError(page['error'])
    return {'players':parse_confirmed_page(page['html'],day,pairs),
            'checked_at':page['checked_at'],'source':'RotoWire shared NBA lineup page',
            'pending':bool(page.get('pending')),'stale':bool(page.get('stale')),'issue':page.get('issue','')}


def download_lineup_page_result(day):
    try:return download_lineup_page(day)
    except (ValueError,OSError,KeyError,TypeError) as exc:
        return {'error':str(exc),'checked_at':time.time()}


class LineupFetchPending(ValueError):pass


_lineup_cache=LineupPageCache(download_lineup_page_result)


def request_lineup_refresh(day):
    from simmah_nba_official_lineups import request_refresh
    request_refresh(day)
    return _lineup_cache.get(day,force=True)


def _download_player_lineups(key):
    from simmah_nba_lineups import download_lineup_status
    day,slate_id,pairs=key
    response=download_lineup_status(slate_id,day,pairs)
    starters={}
    for team in {key[1] for key in response['players']}:
        group={key:value for key,value in response['players'].items()
               if key[1]==team and explicit_true(value.get('Expected Starter'))}
        if len(group)==5:starters.update(group)
    if not starters:raise ValueError('Player feed supplied no complete expected starting five')
    return {**response,'players':starters,'source':'RotoWire player-data lineup feed'}


_player_lineup_cache=LineupPageCache(_download_player_lineups)


def cached_player_lineups(st,day,pairs,force=False):
    record=st.session_state.get('nba_rotowire_cache',{})
    identity=record.get('identity',())
    if len(identity)<2 or identity[1]!=day or not str(record.get('slate_id','')).isdigit():
        raise ValueError('No matching RotoWire player-feed slate ID available')
    key=(day,str(record['slate_id']),tuple(sorted(pairs)))
    result=_player_lineup_cache.get(key,force=force)
    if not result.get('players') and result.get('pending'):
        raise LineupFetchPending('Checking RotoWire player-data lineups')
    if result.get('error'):raise ValueError(result['error'])
    return result


def current_confirmed_pool(st,pool,day,pairs):
    scope=(day,tuple(sorted({tuple(sorted(map(team_key,p))) for p in pairs})))
    saved=st.session_state.get('nba_confirmed_last_good',{})
    stale=False;issue='';pending=False
    response=saved.get('response',{}) if saved.get('scope')==scope else {}
    try:
        primary=cached_confirmed_status(st,day,pairs)
        pending=bool(primary.get('pending'));stale=pending or bool(primary.get('stale'))
        issue=primary.get('issue','')
        # Do not overwrite newer saved fallback data with an older stale page.
        if not stale or primary.get('checked_at',0)>=response.get('checked_at',0):
            response=primary
    except (ValueError,OSError,KeyError,TypeError) as exc:
        issue=str(exc);pending=isinstance(exc,LineupFetchPending)
        stale=True
    if stale:
        try:
            fallback=cached_player_lineups(st,day,pairs)
            fallback_pending=bool(fallback.get('pending'))
            fallback_stale=fallback_pending or bool(fallback.get('stale'))
            if not fallback_stale or fallback.get('checked_at',0)>=response.get('checked_at',0):
                response=fallback
                pending=fallback_pending;stale=fallback_stale
                issue=fallback.get('issue','')
        except LineupFetchPending:
            pending=True
        except (ValueError,OSError,KeyError,TypeError) as fallback_error:
            issue+='; player-data fallback: '+str(fallback_error)
    if stale:
        from simmah_nba_official_lineups import cached_lineups
        try:
            official=cached_lineups(day,pairs)
            official_pending=bool(official.get('pending'))
            official_stale=official_pending or bool(official.get('stale'))
            if official.get('players') and (not official_stale or official.get('checked_at',0)>=response.get('checked_at',0)):
                response=official;pending=official_pending;stale=official_stale
                issue=official.get('issue','')
            elif official_pending:
                pending=True
        except (ValueError,OSError,KeyError,TypeError) as official_error:
            issue+='; NBA.com fallback: '+str(official_error)
    if response.get('players'):
        st.session_state['nba_confirmed_last_good']={'scope':scope,'response':response}
    if not response and pool.attrs.get('slate_date')!=day:
        pool=pool.copy()
        pool['Expected Starter']=False
        pool['Starter Confirmed']=False
    view=apply_confirmed_status(pool,response.get('players',{}))
    view.attrs['lineup_status_pending']=pending
    if stale:view['Lineup Status Stale']=True
    return view,{**response,'stale':stale,'pending':pending,'issue':issue}


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

