"""Retrospective game-script associations; never imported by production."""
import gzip,json,sys
from pathlib import Path
import numpy as np,pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.expand_minutes_evidence_offline import player_key

PERSONAL={'Shooting Foul','Personal Foul','Offensive Foul','Loose Ball Foul','Personal Take Foul','Clear Path Foul','Away from Play Foul','Transition Take Foul','Double Personal Foul','Flagrant Foul Type 1','Flagrant Foul Type 2'}
def seconds(value):
    parts=str(value).split(':')
    return float(parts[0])*60+float(parts[1]) if len(parts)==2 else float(parts[0])

def game_context(data):
    events=data.get('events',data.get('plays',[]));box=data['boxscore'];lookup={}
    for team in box['players']:
        for group in team['statistics']:
            for p in group['athletes']:
                lookup[str(p['athlete']['id'])]=player_key(p['athlete']['displayName'],team['team']['abbreviation'])
    fouls={};q4=[];unknown=set()
    for e in events:
        period=e.get('period',{}).get('number',0)
        if period==4:
            try:q4.append((seconds(e['clock']['displayValue']),abs(e['homeScore']-e['awayScore'])))
            except (KeyError,ValueError,TypeError):pass
        typ=e.get('type',{}).get('text','')
        if 'foul' in typ.lower() and typ not in PERSONAL and not any(x in typ.lower() for x in ['technical','turnover','drawn','violation']):unknown.add(typ)
        if typ not in PERSONAL:continue
        ps=e.get('participants',[])
        if len(ps)!=1 and typ!='Double Personal Foul':continue
        for participant in ps:
            key=lookup.get(str(participant['athlete']['id']))
            if key:fouls.setdefault(key,[]).append(period)
    # Use the last score observation at or before the 6:00 fourth-quarter checkpoint.
    before=[(s,m) for s,m in q4 if s>=360];m6=min(before,key=lambda x:x[0])[1] if before else None
    return fouls,m6,sorted(unknown)

def run(root):
    root=Path(root);out=root/'minutes-script-results';out.mkdir(exist_ok=True)
    f=pd.read_csv(root/'minutes-role-results/expanded_roles/role_player_rows.csv',dtype={'game_id':str,'package':str})
    games={};unknown=set()
    paths=list((root/'simmah-nba-clock/data/nba_pbp').glob('*/*.json.gz'))+list((root/'nov13-lineup-research').glob('401*.json.gz'))
    for path in paths:
        d=json.load(gzip.open(path));gid=str(d.get('event_id',d.get('header',{}).get('id')))
        if gid not in set(f.game_id):continue
        ledger,m6,u=game_context(d);games[gid]=(ledger,m6);unknown.update(u)
    f['q4_margin_at6']=[games.get(g,({},None))[1] for g in f.game_id]
    f['pbp_personal_fouls']=[len(games.get(g,({},None))[0].get((n,t),[])) for g,n,t in zip(f.game_id,f.name_key,f.team_key)]
    f['foul_ledger_verified']=f.pbp_personal_fouls==f.personal_fouls
    flags=[]
    for r in f.itertuples():
        periods=games.get(r.game_id,({},None))[0].get((r.name_key,r.team_key),[])
        flags.append(bool(r.foul_ledger_verified and (sum(p<=1 for p in periods)>=2 or sum(p<=2 for p in periods)>=3 or sum(p<=3 for p in periods)>=4 or len(periods)>=6)))
    f['foul_threshold_proxy']=flags
    f['blowout_proxy']=(f.final_margin>=20)|(f.q4_margin_at6>=20)
    f['competitive_proxy']=(f.final_margin<=10)&(f.q4_margin_at6<=10)
    # Latest pretip physical-team snapshot avoids treating both sites as independent games.
    f['captured_at']=pd.to_datetime(f.captured_at,utc=True,format='mixed')
    latest=f.groupby(['game_id','team_key','package']).captured_at.first().reset_index().sort_values(['captured_at','package']).drop_duplicates(['game_id','team_key'],keep='last')
    primary=f.merge(latest[['game_id','team_key','package']],on=['game_id','team_key','package'],validate='many_to_one')
    primary['rank_pregame_minutes']=primary.groupby(['game_id','team_key']).projected_minutes.rank(method='first',ascending=False)
    gains=primary[primary.rank_pregame_minutes<=7].groupby(['game_id','team_key']).delta.sum()
    primary['top7_net_minute_gain']=[gains.get((g,t),np.nan) for g,t in zip(primary.game_id,primary.team_key)]
    primary['tightening_consistent_proxy']=primary.competitive_proxy&(primary.top7_net_minute_gain>0)&(primary.rank_pregame_minutes>7)&(primary.delta< -5)
    def summary(x):
        x=x[(x.overtimes==0)&(x.delta< -5)&(x.projected_minutes>=18)]
        return {'n':len(x),'games':x.game_id.nunique(),'by_tier':x.tier.value_counts().to_dict(),'blowout_proxy':int(x.blowout_proxy.sum()),'foul_threshold_proxy_verified':int(x.foul_threshold_proxy.sum()),'both':int((x.blowout_proxy&x.foul_threshold_proxy).sum()),'competitive_proxy':int(x.competitive_proxy.sum()),'neither_blowout_nor_foul':int((~x.blowout_proxy&~x.foul_threshold_proxy).sum()),'foul_ledger_mismatch':int((~x.foul_ledger_verified).sum()),'missing_q4_checkpoint':int(x.q4_margin_at6.isna().sum()),'coverage80':float(x.covered.mean())}
    result={'offline_only':True,'primary':summary(primary),'sites':{k:summary(x) for k,x in f.groupby('platform')},'primary_tightening_consistent':int(primary[primary.overtimes==0].tightening_consistent_proxy.sum()),'unknown_foul_types':sorted(unknown),'definitions':{'blowout':'final margin >=20 OR margin >=20 at Q4 6:00 checkpoint','competitive':'final margin <=10 AND Q4 6:00 margin <=10','foul':'PBP personal-foul ledger equals final PF; >=2 Q1, >=3 through Q2, >=4 through Q3, or >=6 final','tightening':'competitive, pregame minutes rank >7, loses >5 minutes, and top7 aggregate minute gain >0'},'limitations':['Associations overlap; no causal assignment','Actual margins/fouls are retrospective labels only','Top7 comparison covers matched positive-projection players, not complete substitution stints','No late-news timestamp attribution; two actual overtime games excluded','This 12-build set is development data, not untouched validation']}
    f.to_csv(out/'all_forecasts_context.csv',index=False);primary.to_csv(out/'primary_context.csv',index=False)
    (out/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':run(sys.argv[1])
