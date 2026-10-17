import io, requests, pandas as pd
url='https://www.dailyfantasyfuel.com/nfl/projections/fanduel/2026-10-15/'
r=requests.get(url,headers={'User-Agent':'Mozilla/5.0'},timeout=30); r.raise_for_status()
for t in pd.read_html(io.StringIO(r.text)):
    if isinstance(t.columns,pd.MultiIndex) and t.shape[1]>=10:
        print('shape',t.shape)
        for i,c in enumerate(t.columns):
            vals=t.iloc[:5,i].astype(str).tolist()
            print(i+1,repr(c),vals)
        break
