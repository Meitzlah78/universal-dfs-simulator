import requests,re,html,json
u='https://www.dailyfantasyfuel.com/nfl?platform=fd&slate=21128'
r=requests.get(u,headers={'User-Agent':'Mozilla/5.0'},timeout=30)
t=r.text
print('status',r.status_code,'len',len(t),'url',r.url)
terms=['Brandon Aubrey','Trey Smack','Jordan Love','CeeDee Lamb','21128','projection','projected','fpts','fantasy_points','slate_id','slateId','player_id']
for term in terms:
 print(term, term.casefold() in t.casefold(), t.casefold().find(term.casefold()))
for name in ['Brandon Aubrey','Trey Smack','Jordan Love','CeeDee Lamb']:
 print('\n===== CONTEXT',name,'=====')
 for m in list(re.finditer(re.escape(name),t,re.I))[:10]:
  s=html.unescape(t[max(0,m.start()-1600):m.end()+2200]).replace('\n',' ')
  print(s[:3800])
print('\n===== 21128 CONTEXT =====')
for m in list(re.finditer('21128',t,re.I))[:20]: print(html.unescape(t[max(0,m.start()-1200):m.end()+1800]).replace('\n',' ')[:3000])
print('\n===== SCRIPT SOURCES =====')
for src in re.findall(r'<script[^>]+src=["\']([^"\']+)',t,re.I): print(html.unescape(src))
print('\n===== URL/API CANDIDATES =====')
patterns=[r'''(?:https?:)?//[^"'<> ]+''',r'''/[A-Za-z0-9_?&=./:-]*(?:api|data|player|projection|slate|optimizer)[A-Za-z0-9_?&=./:-]*''']
out=set()
for p in patterns:
 for x in re.findall(p,t,re.I):
  x=html.unescape(x)
  if any(k in x.casefold() for k in ['api','data','player','projection','slate','optimizer']): out.add(x)
for x in sorted(out): print(x[:800])
