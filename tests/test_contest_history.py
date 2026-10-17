from pathlib import Path
import json,tempfile,unittest
import numpy as np,pandas as pd
from simmah_contest_history import (parse_lineups,ingest_frames,features_from_lineups,
    merge_stores,load_store,save_store,update_store,matching_profiles,calibrate_field,name_key)


class ContestHistoryTest(unittest.TestCase):
    def classic(self):
        return pd.DataFrame({'Rank':[1,2,3,3],'EntryId':[1,2,3,3], 'EntryName':['a','b','c','c'],
            'Lineup':['QB Q RB R1 RB R2 WR W1 WR W2 WR W3 TE T FLEX F DST D1',
                      'DST D1 FLEX F QB Q RB R1 RB R2 TE T WR W1 WR W2 WR W3',
                      'QB Q2 RB R1 RB R2 WR W1 WR W2 WR W4 TE T FLEX F DST D2',
                      'QB Q2 RB R1 RB R2 WR W1 WR W2 WR W4 TE T FLEX F DST D2']})

    def test_real_lineup_parsing_and_duplicate_entries(self):
        lineups=parse_lineups(self.classic())
        self.assertEqual(len(lineups),3)
        profiles=ingest_frames([self.classic()],'fixture')
        p=profiles[0]
        self.assertEqual(p['format'],'DK_CLASSIC')
        self.assertEqual(p['lineups'],3)
        self.assertEqual(p['unique_lineups'],2)
        self.assertEqual(set(p['features']),{'ownership_sum','ownership_product_log'})
        encoded=json.dumps(p)
        self.assertNotIn('EntryName',encoded)
        self.assertNotIn('W4',encoded)

    def test_mode_inferred_from_lineup_body(self):
        frame=pd.DataFrame({'Rank':[1],'EntryId':[1], 'EntryName':['a'],
            'Lineup':['CPT Player One FLEX Player Two FLEX Player Three FLEX Player Four FLEX Player Five FLEX Player Six']})
        p=ingest_frames([frame],'single')[0]
        self.assertEqual(p['format'],'DK_SHOWDOWN')
        self.assertEqual(p['roster_size'],6)
        with self.assertRaises(ValueError):ingest_frames([frame],'wrong',mode='Classic')

    def test_metadata_is_required_for_salary_and_team_features(self):
        lineups=parse_lineups(self.classic())
        metadata={name_key(name):{'Salary':5000,'Team':'A','Opponent':'B','Position':slot} for lineup in lineups for slot,name in lineup}
        metadata['w1']['Position']='WR'
        feats=features_from_lineups(lineups,metadata)
        self.assertTrue((feats['salary_left']==5000).all())
        self.assertIn('qb_pass_catcher_stack_count',feats)
        self.assertNotIn('salary_left',features_from_lineups(lineups))

    def test_persistence_dedup_and_context_guards(self):
        p=ingest_frames([self.classic()],'fixture',fee=.10,max_entries=20)[0]
        store={'schema':1,'contests':[p]}
        self.assertEqual(len(merge_stores(store,store)['contests']),1)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'history.json';save_store(path,store)
            restored=load_store(path)
            self.assertEqual(restored,store)
        self.assertEqual(len(matching_profiles(store,'DraftKings','Classic',fee=.1,max_entries=20,roster_size=9)),1)
        self.assertFalse(matching_profiles(store,'DraftKings','Showdown',fee=.1,roster_size=6))
        self.assertFalse(matching_profiles(store,'FanDuel','Full Roster',fee=.1,roster_size=9))
        self.assertFalse(matching_profiles(store,'DraftKings','Classic',fee=100,roster_size=9))
        self.assertFalse(matching_profiles(store,'DraftKings','Classic',fee=.1,max_entries=150,roster_size=9))

    def test_invalid_backup_rejected(self):
        with self.assertRaises(ValueError):merge_stores({'schema':999,'contests':[]})
        p=ingest_frames([self.classic()],'fixture')[0]
        p['features']['ownership_sum']['counts'][0]=-1
        with self.assertRaises(ValueError):merge_stores({'schema':1,'contests':[p]})

    def test_calibration_samples_without_inventing_duplicates(self):
        profile=ingest_frames([self.classic()],'fixture')[0]
        # An oversized proposal set contains each synthetic lineup once.
        rows=[];players=[]
        for i in range(100):
            row={}
            for j,slot in enumerate(['QB','RB1','RB2','WR1','WR2','WR3','TE','FLEX','DST']):
                name=f'p{i}_{j}';row[slot]=name
                players.append(dict(Name=name,Position=slot.rstrip('123'),Team=str(j),Opponent=str(j+1),Salary=5000))
            rows.append(row)
        field=pd.DataFrame(rows);slots=list(field.columns)
        selected,provenance=calibrate_field(field,pd.DataFrame(players),slots,[profile],50,np.random.default_rng(4))
        self.assertTrue(provenance['applied'])
        self.assertEqual(len(selected),50)
        self.assertEqual(len(selected.drop_duplicates()),50)
        self.assertIn('ownership_sum',provenance['features'])

    def test_csv_zip_and_row_order_share_contest_identity(self):
        original=self.classic()
        first=ingest_frames([original],'zip-hash')[0]
        second=ingest_frames([original.iloc[::-1]],'csv-hash')[0]
        self.assertEqual(first['id'],second['id'])
        self.assertEqual(len(merge_stores({'schema':1,'contests':[first]},{'schema':1,'contests':[second]})['contests']),1)

    def test_saved_imports_merge_instead_of_overwriting_other_sessions(self):
        first=ingest_frames([self.classic()],'first')[0]
        frame=self.classic().copy();frame['EntryId']+=100
        second=ingest_frames([frame],'second')[0]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'history.json'
            update_store(path,{'schema':1,'contests':[first]})
            update_store(path,{'schema':1,'contests':[second]})
            self.assertEqual(len(load_store(path)['contests']),2)

    def test_fanduel_single_game_and_roster_size_guard(self):
        frame=pd.DataFrame({'Rank':[1],'MVP':['a'],'FLEX1':['b'],'FLEX2':['c'],'FLEX3':['d'],'FLEX4':['e'],'FLEX5':['f']})
        p=ingest_frames([frame],'fd')[0]
        store={'schema':1,'contests':[p]}
        self.assertEqual(p['format'],'FD_SINGLE')
        self.assertTrue(matching_profiles(store,'FanDuel','Single Game',roster_size=6))
        self.assertFalse(matching_profiles(store,'FanDuel','Single Game',roster_size=5))

    def test_learned_distribution_changes_field_selection(self):
        from simmah_contest_history import BINS
        slots=['QB','RB1','RB2','WR1','WR2','WR3','TE','FLEX','DST']
        rows=[]
        for i in range(1000):
            row={slot:(f'common{j}' if i<500 else f'rare{i}_{j}') for j,slot in enumerate(slots)}
            row['group']='concentrated' if i<500 else 'diffuse';rows.append(row)
        field=pd.DataFrame(rows)
        names=set(field[slots].to_numpy().ravel());pool=pd.DataFrame({'Name':list(names)})
        edges=BINS['ownership_sum'];hist=np.zeros(len(edges)-1,dtype=int)
        hist[np.searchsorted(edges,450,side='right')-1]=1000
        profile={'format':'DK_CLASSIC','id':'toy','lineups':1000,'features':{
            'ownership_sum':{'edges':edges.tolist(),'counts':hist.tolist(),'count':1000,'mean':450.,'std':1.}}}
        selected,info=calibrate_field(field,pool,slots,[profile],500,np.random.default_rng(7))
        self.assertTrue(info['applied'])
        self.assertGreater((selected['group']=='concentrated').sum(),275)


if __name__=='__main__':unittest.main()
