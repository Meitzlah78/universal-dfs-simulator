"""Offline structural acceptance checks for NFL DK/FD native entry CSVs.

Player metadata must come from the original site's salary file, keyed by exact
site player ID. DK special-role IDs have already-multiplied salary and declare
roster_position=CPT/FLEX. FD uses base salaries and a 1.5x MVP salary multiplier.
This validates generated files, not the site's eventual upload acceptance.
"""
from collections import Counter
import csv
import io
import math
import re

from simmah_contest_history import name_key


def _rows(value):
    if isinstance(value,bytes):
        value=value.decode('utf-8-sig')
    rows=list(csv.reader(io.StringIO(value)))
    if not rows:
        raise ValueError('Empty entry template')
    header=[v.strip().casefold() for v in rows[0]]
    def column(options):
        found=[i for i,c in enumerate(header) if c in options]
        if len(found)!=1:
            raise ValueError('Missing or ambiguous entry metadata column')
        return found[0]
    entry=column({'entry_id','entry id','entryid'})
    contest=column({'contest_id','contest id','contestid'})
    entries=[];end=len(rows)
    for i,row in enumerate(rows[1:],1):
        if not row or not row[0].strip():
            end=i;break
        if len(row)<=max(entry,contest) or not re.fullmatch(r'[1-9]\d*',row[entry].strip()):
            raise ValueError('Entry ID must be an exact positive integer string')
        entries.append(row)
    ids=[r[entry].strip() for r in entries]
    if len(ids)!=len(set(ids)):
        raise ValueError('Duplicate original or exported Entry ID')
    return rows[0],entries,rows[end:],entry,contest


def _player_id(value):
    match=re.fullmatch(r'(?:.*\()?([1-9]\d*(?:-[1-9]\d*)?)\)?',str(value).strip())
    if not match:
        raise ValueError('Invalid exported player ID')
    return match[1]


def verify_entry_export(original_csv, exported_csv, players, site, mode,
                        *, contest_ids=None, expected_assignments=None):
    """Reject row loss, remapping, illegal roles/salary and wrong assignments.

    contest_ids explicitly defines export scope. Entries outside that scope are
    excluded by design, rather than incorrectly reported as missing replacements.
    expected_assignments maps Entry ID to exact ordered player IDs; without it
    legality can be checked but assignment fidelity is reported as unverified.
    """
    if site not in ('DraftKings','FanDuel') or mode not in ('Classic','Full Roster','Showdown','Single Game'):
        raise ValueError('Unsupported NFL export format')
    if (site=='DraftKings' and mode not in ('Classic','Showdown')) or (site=='FanDuel' and mode not in ('Full Roster','Single Game')):
        raise ValueError('Site and mode do not match')
    single=mode in ('Showdown','Single Game')
    original, before, original_footer, entry, contest=_rows(original_csv)
    exported, after, footer, export_entry, export_contest=_rows(exported_csv)
    def normalized_header(header):
        return [re.sub(r'\.\d+$','',re.sub(r'^Unnamed: \d+$','',v)).strip() for v in header]
    dk_width=10 if single else 13
    header_matches = original==exported or (site=='DraftKings' and (
        normalized_header(original)==normalized_header(exported) or
        (len(exported)==dk_width and normalized_header(original[:dk_width])==normalized_header(exported))))
    if not header_matches or (entry,contest)!=(export_entry,export_contest):
        raise ValueError('Native template header changed')
    if footer!=original_footer and not (site=='DraftKings' and not footer):
        raise ValueError('Template reference/instruction rows changed')
    allowed=None if contest_ids is None else set(map(str,contest_ids))
    wanted={r[entry].strip():r for r in before if allowed is None or r[contest].strip() in allowed}
    actual={r[entry].strip():r for r in after}
    if not wanted or set(actual)!=set(wanted):
        raise ValueError('Export dropped or introduced scoped Entry IDs')
    if single:
        aliases=([{'cpt'},{'flex'},{'flex'},{'flex'},{'flex'},{'flex'}] if site=='DraftKings' else
                 [{'mvp','mvp - 1.5x points'},{'anyflex','flex'},{'anyflex','flex'},{'anyflex','flex'},{'anyflex','flex'},{'anyflex','flex'}])
        roles=['CPT' if site=='DraftKings' else 'MVP']+['FLEX']*5
    else:
        aliases=[{'qb'},{'rb'},{'rb'},{'wr'},{'wr'},{'wr'},{'te'},{'flex'},{'dst','d','def'}]
        roles=['QB','RB','RB','WR','WR','WR','TE','FLEX','DST']
    columns=[]
    for options in aliases:
        found=next((i for i,h in enumerate(original) if re.sub(r'\.\d+$','',h.strip().casefold()) in options and i not in columns),None)
        if found is None:
            raise ValueError('Missing native roster slot')
        columns.append(found)
    cap=50000 if site=='DraftKings' else 60000
    eligible={'QB':{'QB'},'RB':{'RB'},'WR':{'WR'},'TE':{'TE'},'FLEX':{'RB','WR','TE'},'DST':{'DST','D','DEF'}}
    for ident,row in actual.items():
        base=wanted[ident]
        if row[contest]!=base[contest]:
            raise ValueError('Entry moved to a different contest')
        same_width=len(row)==len(base) or (site=='DraftKings' and len(row)==dk_width and len(base)>=dk_width)
        if not same_width or any(row[i]!=base[i] for i in range(len(row)) if i not in columns):
            raise ValueError('Entry metadata or instructions changed')
        ids=[_player_id(row[i]) for i in columns]
        if expected_assignments is not None and ids!=list(map(str,expected_assignments.get(ident,[]))):
            raise ValueError('Assigned roster changed for Entry ID '+ident)
        if any(p not in players for p in ids):
            raise ValueError('Player ID missing from original salary metadata')
        roster=[players[p] for p in ids]
        names=[name_key(p['name']) for p in roster]
        if len(set(names))!=len(names) or not all(names):
            raise ValueError('Same athlete appears more than once')
        total=0.
        for i,(p,role) in enumerate(zip(roster,roles)):
            salary=float(p['salary'])
            if not math.isfinite(salary) or salary<0:
                raise ValueError('Invalid original salary')
            total+=salary*(1.5 if single and site=='FanDuel' and i==0 else 1.)
            if single and site=='DraftKings':
                if p.get('roster_position')!=role:
                    raise ValueError('DK Captain/FLEX player ID used in wrong slot')
            elif not single:
                if not set(p['positions']) & eligible[role]:
                    raise ValueError('Player is in an ineligible position slot')
            if site=='FanDuel' and ids[i].split('-',1)[0]!=row[contest].split('-',1)[0]:
                raise ValueError('Player belongs to another FanDuel slate')
        if total>cap+1e-8:
            raise ValueError('Lineup exceeds site salary cap')
        if not single:
            teams=Counter(p['team'] for p in roster)
            if len(teams)<2 or (site=='FanDuel' and max(teams.values())>4):
                raise ValueError('Full-roster team composition is illegal')
            if site=='DraftKings' and (any(not p.get('game') for p in roster) or len({p['game'] for p in roster})<2):
                raise ValueError('DK Classic requires players from at least two games')
        if single and len({p['team'] for p in roster})!=2:
            raise ValueError('Single-game lineup must contain both teams')
    return dict(passed=True,entries_checked=len(after),excluded_entries=len(before)-len(wanted),
        contest_counts=dict(Counter(r[contest] for r in after)),salary_cap=cap,
        assignment_parity_verified=expected_assignments is not None,
        reference_rows_preserved=footer==original_footer,
        site_upload_acceptance_verified=False)
