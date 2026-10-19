import unittest
import numpy as np
import pandas as pd
from simmah_contest_history import features_from_lineups,ingest_frames,calibrate_field


class ShowdownLearningTest(unittest.TestCase):
    def test_captain_popularity_uses_captain_slot_only_and_ignores_scores(self):
        rows=[ [('CPT','a')]+[('FLEX',p) for p in ['b','c','d','e','f']] for _ in range(3)]
        rows += [[('CPT','b')]+[('FLEX',p) for p in ['a','c','d','e','f']]]
        feats=features_from_lineups(rows)
        np.testing.assert_array_equal(feats.captain_popularity,[75,75,75,25])
        frame=pd.DataFrame({'Rank':[1,2,3,4],'EntryId':[1,2,3,4],
            'Lineup':[' '.join(s+' '+n for s,n in row) for row in rows],'Points':[100,80,60,40]})
        first=ingest_frames([frame],'x',platform='DraftKings',mode='Showdown')[0]
        frame['Points']=[-1,9999,0,30];frame['Rank']=[4,3,2,1]
        second=ingest_frames([frame],'x',platform='DraftKings',mode='Showdown')[0]
        self.assertEqual(first['features'],second['features'])
        self.assertEqual(first['features']['captain_popularity']['count'],4)

    def test_full_roster_has_no_captain_feature(self):
        feats=features_from_lineups([[('QB','a'),('RB','b'),('WR','c')]])
        self.assertNotIn('captain_popularity',feats)

    def test_learned_captain_concentration_changes_opponent_selection(self):
        from simmah_contest_history import BINS
        slots=['Captain','Flex1','Flex2','Flex3','Flex4','Flex5']
        field=pd.DataFrame([dict(zip(slots,['chalk' if i<600 else 'rare'+str(i),*['f'+str(j) for j in range(5)]])) for i in range(1000)])
        edges=BINS['captain_popularity'];hist=np.zeros(len(edges)-1,int);hist[np.searchsorted(edges,60,side='right')-1]=1000
        profile={'format':'DK_SHOWDOWN','id':'fixture','lineups':1000,'features':{'captain_popularity':{'counts':hist.tolist()}}}
        result,info=calibrate_field(field,pd.DataFrame({'Name':pd.unique(field[slots].to_numpy().ravel())}),slots,[profile],300,np.random.default_rng(2))
        self.assertIn('captain_popularity',info['features'])
        self.assertGreater((result.Captain=='chalk').sum(),210)
        self.assertEqual(len(result),300)
