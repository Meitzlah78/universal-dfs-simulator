import re, requests, json
from html import unescape

H={'User-Agent':'Mozilla/5.0'}
urls=[
 'https://www.dailyfantasyfuel.com/nfl/showdown-single-game-projections/fanduel',
 'https://www.dailyfantasyfuel.com/data/slates/recent/nfl/fanduel',
]
for url in urls:
    print('\nURL',url)
    r=requests.get(url,headers=H,timeout=30)
    print('status',r.status_code,'len',len(r.text))
    text=r.text
    if 'data/slates' in url:
        print(text[:20000])
        continue
    # Print every URL/query fragment mentioning slate and surrounding select/option values.
    hits=[]
    for m in re.finditer(r'.{0,180}(?:slate|showdown|single-game).{0,240}', text, re.I|re.S):
        s=re.sub(r'\s+',' ',unescape(m.group(0))).strip()
        if s not in hits:
            hits.append(s)
    print('HITS')
    for s in hits[:100]: print(s)
    print('HREFS')
    for href in re.findall(r'href=["\']([^"\']+)["\']', text, re.I):
        if 'slate' in href.lower() or 'showdown' in href.lower() or 'single-game' in href.lower():
            print(unescape(href))
    print('OPTIONS')
    for value,label in re.findall(r'<option[^>]*value=["\']([^"\']*)["\'][^>]*>(.*?)</option>', text, re.I|re.S):
        clean=re.sub(r'<[^>]+>',' ',label); clean=re.sub(r'\s+',' ',unescape(clean)).strip()
        if value or clean: print(repr(value), repr(clean))
