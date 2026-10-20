"""Read-only, on-demand Underdog NBA news. Never modifies roster inputs."""
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import streamlit as st


class NewsUnavailable(Exception):
    pass


def _get(path, token, params=None):
    try:
        response = requests.get('https://api.x.com/2/' + path,
            headers={'Authorization': 'Bearer ' + token}, params=params,
            timeout=(3, 8), allow_redirects=False)
        if response.status_code != 200:
            explanations = {401: 'token rejected', 402: 'API credits required',
                403: 'access denied; check app permissions and credits',
                429: 'rate limit reached; try again later'}
            raise NewsUnavailable('X API HTTP %s: %s' % (response.status_code,
                explanations.get(response.status_code, 'temporarily unavailable')))
        payload = response.json()
        if not isinstance(payload, dict) or payload.get('errors'):
            raise NewsUnavailable('X returned an incomplete response; try again later.')
        return payload
    except (requests.RequestException, ValueError):
        # Never expose response bodies, request headers, or the token in the UI.
        raise NewsUnavailable('X API connection failed; try again later.') from None


@st.cache_data(ttl=86400, show_spinner=False, max_entries=8)
def _account(credential_id, _token):
    data = _get('users/by/username/UnderdogNBA', _token).get('data', {})
    account_id = str(data.get('id', ''))
    if not account_id.isdigit():
        raise NewsUnavailable('Underdog NBA account lookup did not return an ID.')
    return account_id


@st.cache_data(ttl=300, show_spinner=False, max_entries=8)
def _posts(credential_id, account_id, _token):
    payload = _get('users/' + account_id + '/tweets', _token,
        {'max_results': 10, 'exclude': 'retweets,replies',
         'tweet.fields': 'created_at', 'user.fields': 'username'})
    posts = payload.get('data', [])
    if not isinstance(posts, list):
        raise NewsUnavailable('X returned an invalid posts response.')
    clean = [{'id': str(p['id']), 'text': str(p.get('text', '')),
              'created_at': str(p.get('created_at', ''))}
             for p in posts if isinstance(p, dict) and str(p.get('id', '')).isdigit()]
    return {'posts': clean, 'checked_at': datetime.now(ZoneInfo('America/New_York')).isoformat()}


def render_underdog_news(st):
    try:
        token = str(st.secrets.get('X_BEARER_TOKEN', '')).strip()
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        token = ''
    if not token:
        import streamlit.components.v1 as components
        feed = components.declare_component('simmah_underdog_nba_news',
            path=str(Path(__file__).parent/'components/underdog_nba_news'))
        feed(key='nba_underdog_x_feed', default=None)
        return
    with st.expander('Underdog NBA — X news & starting lineups'):
        st.caption('Read-only news. Posts do not automatically change injuries, confirmed starters, or projections.')
        st.link_button('OPEN @UnderdogNBA', 'https://x.com/UnderdogNBA')
        enabled = st.checkbox('Load latest X news', key='nba_x_news_enabled',
            help='Reads up to 10 posts. Cached for five minutes across both NBA formats. X usage charges may apply.')
        if not enabled:
            return
        # Token is excluded from cached arguments; its fingerprint separates credentials.
        credential_id = sha256(token.encode()).hexdigest()
        try:
            with st.spinner('Loading Underdog NBA news…'):
                account_id = _account(credential_id, token)
                result = _posts(credential_id, account_id, token)
            checked = datetime.fromisoformat(result['checked_at'])
            st.caption('X API connected · Last checked ' + checked.strftime('%b %d, %I:%M:%S %p %Z')
                + ' · Refreshes on app activity after five minutes; no background polling.')
            if not result['posts']:
                st.info('No recent original posts returned by X.')
            for post in result['posts']:
                st.text(post['text'])
                st.link_button('View post · ' + post['created_at'],
                    'https://x.com/UnderdogNBA/status/' + post['id'], key='nba_x_post_' + post['id'])
        except NewsUnavailable as exc:
            st.warning(str(exc))
