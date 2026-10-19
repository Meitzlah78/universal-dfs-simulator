import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import numpy as np
import pandas as pd
from simmah_benchmark import (freeze_bundle,load_bundle,validate_players,audit_rosters,
    replace_portfolio,read_completed_standings,SLOTS)


def fixture():
    positions=['QB','RB','RB','WR','WR','WR','TE','TE','DST']
    teams=['A','B','C','A','D','E','F','G','H']
    players=pd.DataFrame([dict(Name='player'+str(i),Position=p,Team=t,Opponent='I',
                              Salary=5000,Projection=10) for i,(p,t) in enumerate(zip(positions,teams))])
    row={slot:'player'+str(i) for i,slot in enumerate(SLOTS)};row['Salary']=45000
    return players,pd.DataFrame([row])


class BenchmarkTest(unittest.TestCase):
    def test_frozen_evidence_detects_mutation_and_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            files={}
            for key in ['players','portfolio','field','standings','contest']:
                source=Path(tmp)/(key+'.txt');source.write_bytes(key.encode());files[key]=source
            root=Path(tmp)/'bundle';manifest=freeze_bundle(files,root)
            loaded,_=load_bundle(root);self.assertEqual(manifest,loaded)
            with self.assertRaises(FileExistsError):freeze_bundle(files,root)
            (root/'players.csv').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'changed'):load_bundle(root)

    def test_ties_share_payouts_and_old_entries_are_removed(self):
        players,portfolio=fixture();scores={n:10 for n in players.Name};scores['player8']=0
        records=[{'EntryName':'me (1/1)','Points':'0'},
                 {'EntryName':'other','Points':'80'}, {'EntryName':'other two','Points':'80'},
                 {'EntryName':'someone','Points':'0','Lineup':''}]
        contest={'owner':'me','entry_fee':1,'field_size':4,'payouts':[[1,1,100],[2,2,50]]}
        result=replace_portfolio(records,portfolio,scores,contest)
        self.assertEqual(result['winnings'],50)
        self.assertEqual(result['lineups'][0]['tied_entries'],3)
        self.assertEqual(result['lineups'][0]['rank'],1)
        self.assertEqual(result['net'],49)
        self.assertEqual(result['roi_pct'],4900)

    def test_missing_actual_scores_and_wrong_entry_count_fail(self):
        players,portfolio=fixture();records=[{'EntryName':'me','Points':0}]
        contest={'owner':'me','entry_fee':1,'field_size':1,'payouts':[[1,1,1]]}
        with self.assertRaisesRegex(ValueError,'scores missing'):replace_portfolio(records,portfolio,{},contest)
        with self.assertRaisesRegex(ValueError,'count'):replace_portfolio([],portfolio,{},contest)

    def test_roster_rules_distinguish_user_constraints_from_opponents(self):
        players,portfolio=fixture();players.loc[8,'Opponent']='A'
        metadata=validate_players(players)
        user=audit_rosters(portfolio,metadata,True);field=audit_rosters(portfolio,metadata,False)
        self.assertEqual(user['violations']['offense_against_defense'],1)
        self.assertEqual(field['violations'],{})
        bad=portfolio.copy();bad['RB1']=bad.QB
        self.assertIn('repeated_player',audit_rosters(bad,metadata,True)['violations'])

    def test_invalid_projections_and_duplicate_names_are_rejected(self):
        players,_=fixture();players.loc[0,'Projection']=np.nan
        with self.assertRaisesRegex(ValueError,'positive'):validate_players(players)
        players,_=fixture();players.loc[1,'Name']=players.loc[0,'Name']
        with self.assertRaisesRegex(ValueError,'duplicate'):validate_players(players)

    def test_projection_baseline_is_repeatable_legal_unique_and_caps_exposure(self):
        from test_candidates import fixture as candidate_fixture
        from simmah_benchmark import projection_baseline
        players,_,_=candidate_fixture();players['Projection']=players.Salary/500
        a=projection_baseline(players,5);b=projection_baseline(players,5)
        pd.testing.assert_frame_equal(a,b)
        self.assertEqual(len(a),5)
        self.assertEqual(a[SLOTS].apply(lambda r:tuple(sorted(r)),axis=1).nunique(),5)
        from collections import Counter
        self.assertLessEqual(max(Counter(a[SLOTS].values.ravel()).values()),4)
        self.assertEqual(audit_rosters(a,validate_players(players),True)['violations'],{})

    def test_incomplete_games_are_not_treated_as_final(self):
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as archive:
            archive.writestr('contest.csv','EntryId,EntryName,TimeRemaining,Points,Player,FPTS\n1,me,60,10,player,10\n')
        with self.assertRaisesRegex(ValueError,'complete'):read_completed_standings(buffer.getvalue())
