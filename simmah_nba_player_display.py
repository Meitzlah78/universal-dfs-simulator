"""Display-only confirmed NBA starter labels; player IDs and raw names stay intact."""
from simmah_nba_game_strip import explicit_true, team_lineup
from simmah_nba_projections import team_key


def player_labels(pool):
    confirmed={team_key(team) for team in pool['Team'].unique()
               if team_lineup(pool,team)['status']=='Confirmed'}
    labels={}
    for _,row in pool.iterrows():
        name=str(row['Name'])
        injury=str(row.get('Injury Status','')).upper()
        if injury in {'Q','QUES','QUESTIONABLE'}:name+=' (Q)'
        elif injury in {'D','DOUBT','DOUBTFUL'}:name+=' (D)'
        if (team_key(row['Team']) in confirmed
                and explicit_true(row.get('Expected Starter',False))
                and explicit_true(row.get('Starter Confirmed',False))):
            name+=' ✅'
        labels[str(row['Player ID'])]=name
    return labels


def display_pool(pool):
    view=pool.copy()
    view['Name']=view['Player ID'].astype(str).map(player_labels(pool))
    return view
