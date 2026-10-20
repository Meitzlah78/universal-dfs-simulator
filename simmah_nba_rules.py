"""Site-specific NBA Classic roster rules; shared simulation and workspace."""
FD_SLOTS=('PG','SG','SF','PF','C','GF','FC','UTIL1','UTIL2')
DK_SLOTS=('PG','SG','SF','PF','C','G','F','UTIL')
BASE=({'PG'},{'SG'},{'SF'},{'PF'},{'C'})
ALL={'PG','SG','SF','PF','C'}


def rules_for(pool=None,platform=None):
    site=platform or (pool.attrs.get('platform','FanDuel') if pool is not None else 'FanDuel')
    if site not in {'DraftKings','FanDuel'}:raise ValueError('Unknown NBA platform')
    dk=site=='DraftKings'
    return {'platform':site,'slots':DK_SLOTS if dk else FD_SLOTS,
            'eligibility':BASE+({'PG','SG'},{'SF','PF'},ALL) if dk else BASE+({'PG','SG','SF','PF'},{'SF','PF','C'},ALL,ALL),
            'salary_cap':50000 if dk else 60000,'max_from_team':8 if dk else 4,
            'min_teams':2 if dk else 3,'min_games':2 if dk else 1,'score_ticks':4 if dk else 10}
