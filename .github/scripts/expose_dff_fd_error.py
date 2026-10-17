import requests, re, html
from urllib.parse import urljoin

url = 'https://www.dailyfantasyfuel.com/nfl?platform=fd&slate=21128'
r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
r.raise_for_status()
text = r.text
print('DFF OPTIMIZER PROBE', r.status_code, len(text), r.url)

for needle in ['21128', 'Trey Smack', 'Brandon Aubrey', 'Jordan Love', 'CeeDee Lamb', '8.2', '8.7', '21.0']:
    print('\n===', needle, '===')
    matches = list(re.finditer(re.escape(needle), text, re.I))
    print('count', len(matches))
    for m in matches[:10]:
        snippet = html.unescape(text[max(0, m.start()-700):m.end()+1200]).replace('\n', ' ')
        print(snippet[:1900])

print('\n=== DATA/API CANDIDATES ===')
candidates = set(re.findall(r'''(?:https?:)?//[^\"'<> ]+|/[A-Za-z0-9_?&=%./:-]*(?:data|api|projection|player|slate)[A-Za-z0-9_?&=%./:-]*''', text, re.I))
for c in sorted(candidates):
    c = html.unescape(c)
    if any(x in c.lower() for x in ['data', 'api', 'projection', 'player', 'slate']):
        print(c[:700])

print('\n=== SCRIPT SOURCES ===')
script_urls = []
for src in re.findall(r'<script[^>]+src=[\"\']([^\"\']+)', text, re.I):
    full = urljoin(url, html.unescape(src))
    script_urls.append(full)
    print(full)

print('\n=== INTERESTING SCRIPT REFERENCES ===')
for script_url in script_urls:
    try:
        js = requests.get(script_url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': url}, timeout=30)
        if js.status_code != 200 or len(js.text) > 5_000_000:
            continue
        hits = []
        for pat in [r'/data/[A-Za-z0-9_?&=%./:-]+', r'/api/[A-Za-z0-9_?&=%./:-]+', r'[A-Za-z0-9_/?&=%.-]*(?:projection|slate|player)[A-Za-z0-9_/?&=%.-]*']:
            hits.extend(re.findall(pat, js.text, re.I))
        hits = sorted(set(x for x in hits if len(x) > 4))
        if hits:
            print('\nSCRIPT', script_url)
            for hit in hits[:200]: print(hit[:700])
    except Exception as exc:
        print('SCRIPT ERROR', script_url, type(exc).__name__, exc)
