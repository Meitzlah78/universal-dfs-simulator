import requests,re
u='https://www.dailyfantasyfuel.com/nfl?platform=fd&slate=21128'
r=requests.get(u,headers={'User-Agent':'Mozilla/5.0'},timeout=30)
print('status',r.status_code,'len',len(r.text),'url',r.url)
for term in ['Brandon Aubrey','Trey Smack','Jordan Love','CeeDee Lamb','21128','data-ppg','projections-listing']:
 print(term, term.casefold() in r.text.casefold(), r.text.casefold().find(term.casefold()))
for name in ['Brandon Aubrey','Trey Smack','Jordan Love']:
 i=r.text.casefold().find(name.casefold())
 if i>=0: print('\nSNIP',name, r.text[max(0,i-1000):i+1500].replace('\n',' ')[:2500])
