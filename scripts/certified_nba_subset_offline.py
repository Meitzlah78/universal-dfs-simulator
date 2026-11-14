"""Exact certified-subset denominators; no dropping unsupported roster members."""
import argparse
import json
from pathlib import Path
import pandas as pd


def select_team_snapshots(audit, priors):
    keys=['package','game_id','team','name']
    x=audit.merge(priors[keys+['supported']],on=keys,how='left',validate='one_to_one')
    result=[]
    for keys,g in x.groupby(['package','game_id','team']):
        # Saved DFS pools are not proof that the full team/game roster is present.
        membership=bool(g.full_membership_verified.eq(True).all()) if 'full_membership_verified' in g else False
        status=bool(g.eligibility_certified.eq(True).all())
        complete_priors=bool(g.supported.eq(True).all())
        result.append({'package':keys[0],'game_id':keys[1],'team':keys[2],
            'pool_n':len(g),'full_membership_verified':membership,
            'all_statuses_certified':status,'all_role_priors_supported':complete_priors,
            'certified':membership and status and complete_priors,
            'allocation_conflict':None})
    return pd.DataFrame(result)


def run(root, metadata, out):
    root,out=Path(root),Path(out);out.mkdir(parents=True,exist_ok=True)
    audit=pd.read_csv(root/'verified-input-audit/roster_metadata_audit.csv',dtype={'game_id':str,'package':str})
    priors=pd.read_csv(root/'role-prior-backfill/role_priors.csv',dtype={'game_id':str,'package':str})
    table=select_team_snapshots(audit,priors)
    games={r['game_id'] for r in json.loads(Path(metadata).read_text()) if r.get('usable') and r.get('season_type_slug')=='regular-season'}
    table['in_159_game_archive']=table.game_id.isin(games)
    table.to_csv(out/'team_snapshot_gate.csv',index=False)
    archive=table[table.in_159_game_archive]
    present=set(archive.game_id)
    # Include games with no saved inputs in coverage, not as allocation failures.
    coverage=[]
    for gid in sorted(games):
        group=archive[archive.game_id==gid]
        coverage.append({'game_id':gid,'saved_team_snapshots':len(group),
            'certified_team_snapshots':int(group.certified.sum()),
            'status':'no_saved_build_inputs' if group.empty else 'certified_team_snapshot_present' if group.certified.any() else 'uncertified_eligible_pool',
            'allocation_conflict':None})
    pd.DataFrame(coverage).to_csv(out/'archive_coverage.csv',index=False)
    summary={'regular_archive_games':len(games),'archive_team_games':2*len(games),
        'archive_games_with_saved_inputs':len(present),'archive_games_without_saved_inputs':len(games-present),
        'archive_unique_team_games_with_saved_inputs':archive.groupby(['game_id','team']).ngroups,
        'archive_team_snapshot_versions':len(archive),'all_saved_games':table.game_id.nunique(),
        'all_unique_saved_team_games':table.groupby(['game_id','team']).ngroups,'all_team_snapshot_versions':len(table),
        'all_snapshots_complete_priors':int(table.all_role_priors_supported.sum()),
        'archive_snapshots_complete_priors':int(archive.all_role_priors_supported.sum()),
        'all_snapshots_complete_verified_statuses':int(table.all_statuses_certified.sum()),
        'certified_team_snapshot_versions':int(table.certified.sum()),
        'certified_archive_team_games':archive[archive.certified].groupby(['game_id','team']).ngroups,
        'allocation_evaluable':int(table.certified.sum()),'allocation_conflict_rate':None,
        'residual_comparison':'not run' if table.certified.any() else 'not evaluable: empty certified subset',
        'cold_start_policy':'uncertified_pool; no numeric fill or player removal',
        'shadow_status':'offline hook implemented; not connected to hosted Simmah or collecting live captures'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('metadata');p.add_argument('out');a=p.parse_args();run(a.root,a.metadata,a.out)
