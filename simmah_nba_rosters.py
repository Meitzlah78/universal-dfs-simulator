"""NBA nine-slot validation and ID-preserving exports; no live build route yet."""
import csv
import io
import math
from collections import Counter
from simmah_nba_import import read_template, SLOTS
from simmah_nba_rules import rules_for

SLOT_COLUMNS=('PG','SG','SF','PF','C','GF','FC','UTIL1','UTIL2')
ELIGIBILITY=({'PG'},{'SG'},{'SF'},{'PF'},{'C'},
             {'PG','SG','SF','PF'},{'SF','PF','C'},
             {'PG','SG','SF','PF','C'},{'PG','SG','SF','PF','C'})


def validate_lineup(pool, player_ids, *, salary_cap, max_from_team, salary_min=0, require_projections=True):
    rules=rules_for(pool);slots=rules['slots'];eligibility=rules['eligibility'];size=len(slots)
    if len(player_ids)!=size or len(set(player_ids))!=size:
        raise ValueError(f'NBA lineup requires {size} distinct players')
    if not isinstance(max_from_team,int) or not 1<=max_from_team<=9:
        raise ValueError('Confirmed NBA team limit is required')
    lookup=pool.set_index('Player ID').to_dict('index')
    if any(pid not in lookup for pid in player_ids):
        raise ValueError('NBA lineup contains an unknown or cross-slate player ID')
    chosen=[lookup[pid] for pid in player_ids]
    for row,allowed,slot in zip(chosen,eligibility,slots):
        if not set(row['Position'].split('/')) & allowed:
            raise ValueError('NBA player is not eligible for '+slot)
        if str(row.get('Injury Status','')).upper() in {'O','OUT','IR','SUSPENDED'}:
            raise ValueError('NBA lineup contains an OUT player')
        if require_projections:
            try:value=float(row.get('Projection'))
            except (ValueError,TypeError):value=float('nan')
            if not math.isfinite(value) or value<=0:
                raise ValueError('NBA lineup contains a zero or missing projection')
    salary=sum(r['Salary'] for r in chosen)
    if not salary_min<=salary<=salary_cap:raise ValueError('NBA lineup salary is outside limits')
    teams=Counter(r['Team'] for r in chosen)
    if len(teams)<rules['min_teams'] or max(teams.values())>max_from_team:
        raise ValueError('NBA lineup violates the confirmed team limit')
    if rules['min_games']>1 and len({tuple(sorted((r['Team'],r['Opponent']))) for r in chosen})<rules['min_games']:
        raise ValueError('DraftKings NBA requires players from at least two games')
    return salary


def export_entries(template, lineups, contest_id, pool, *, salary_cap, max_from_team):
    """Replace only the selected contest's roster cells, preserving other bytes' values.

    Lineups contain the original composite FanDuel IDs, never player names or
    reformatted floats. CSV serialization may change quoting; all non-roster cell
    values and the embedded player table are preserved.
    """
    slate=read_template(template)
    rows=list(csv.reader(io.StringIO(template.decode('utf-8-sig'))))
    dk=rules_for(pool)['platform']=='DraftKings';size=len(rules_for(pool)['slots']);cid_col=2 if dk else 1
    targets=[i for i,r in enumerate(rows[1:],1) if len(r)>=4+size and r[0].isdigit() and r[cid_col]==str(contest_id)]
    if not targets or len(lineups)!=len(targets):
        raise ValueError('Exactly one NBA lineup per reserved entry is required')
    template_ids=set(slate['players']['Player ID'])
    if set(pool['Player ID'])!=template_ids:raise ValueError('NBA export pool differs from entry template')
    seen=set()
    for i,lineup in zip(targets,lineups):
        ids=list(map(str,lineup))
        if any(pid not in template_ids for pid in ids):raise ValueError('NBA export player is from another slate')
        validate_lineup(pool,ids,salary_cap=salary_cap,max_from_team=max_from_team)
        canonical=tuple(sorted(ids))
        if canonical in seen:raise ValueError('Duplicate NBA portfolio lineup')
        seen.add(canonical)
        rows[i][4:4+size]=ids
    output=io.StringIO(newline='')
    csv.writer(output,lineterminator='\r\n').writerows(rows)
    return output.getvalue().encode('utf-8')
