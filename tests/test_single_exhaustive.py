import itertools,unittest
import numpy as np,pandas as pd
from simmah_single_exhaustive import enumerate_lineups,prepare

class ExhaustiveTests(unittest.TestCase):
    def pool(self,n=8):
        return pd.DataFrame({'Player ID':[str(i) for i in range(n)],'Salary':[5000+i*800 for i in range(n)],'Team':['A']*(n//2)+['B']*(n-n//2),'Projection':[10]*n,'Injury Status':['Active']*n})
    def test_matches_independent_bruteforce_both_sites(self):
        for site,cap in [('dk',50000),('fd',60000)]:
            pool=self.pool();actual={};expected={}
            for indices,costs in enumerate_lineups(pool,site,min_salary=43000,batch_sets=3):
                for row,cost in zip(indices,costs):
                    key=(int(row[0]),tuple(sorted(map(int,row[1:]))));self.assertNotIn(key,actual);actual[key]=cost
            for special in range(len(pool)):
                for flex in itertools.combinations([i for i in range(len(pool)) if i!=special],5):
                    ids=[special,*flex];cost=pool.Salary.iloc[special]*1.5+pool.Salary.iloc[list(flex)].sum()
                    if 43000<=cost<=cap and pool.Team.iloc[ids].nunique()==2:expected[(special,flex)]=cost
            self.assertEqual(actual,expected)
    def test_six_players_have_six_role_assignments(self):
        p=self.pool(6);p['Salary']=5000
        self.assertEqual(sum(len(x) for x,_ in enumerate_lineups(p,'dk')),6)
    def test_injury_projection_filters_and_questionable(self):
        p=self.pool();p.loc[0,'Injury Status']='Out';p.loc[1,'Projection']=0;p.loc[2,'Injury Status']='Questionable'
        rows=np.concatenate([x for x,_ in enumerate_lineups(p,'fd')])
        self.assertFalse(np.isin(rows,[0,1]).any());self.assertTrue((rows==2).any())
    def test_explicit_captain_salary(self):
        p=self.pool(6);p['Salary']=5000;p['CaptainSalary']=10000
        for _,costs in enumerate_lineups(p,'dk'):self.assertTrue((costs==35000).all())
    def test_reject_bad_identity_and_teams(self):
        p=self.pool();p.loc[0,'Player ID']='1'
        with self.assertRaises(ValueError):prepare(p,'fd')
        p=self.pool();p['Team']='A'
        with self.assertRaises(ValueError):prepare(p,'dk')
    def test_batch_size_does_not_change_support(self):
        p=self.pool()
        def keys(batch):return {(int(r[0]),tuple(sorted(map(int,r[1:])))) for rows,_ in enumerate_lineups(p,'fd',batch_sets=batch) for r in rows}
        self.assertEqual(keys(1),keys(1000))

    def test_special_whitelist_preserves_all_flex_combinations(self):
        p=self.pool()
        full={(tuple(row),cost) for rows,costs in enumerate_lineups(p,'fd') for row,cost in zip(rows,costs) if row[0] in (1,4)}
        restricted={(tuple(row),cost) for rows,costs in enumerate_lineups(p,'fd',special_player_ids=['1','4']) for row,cost in zip(rows,costs)}
        self.assertEqual(full,restricted)
        self.assertTrue(any(0 in row[1:] for row,_ in restricted))

    def test_invalid_special_ids_fail(self):
        for ids in ([],['missing']):
            with self.assertRaises(ValueError):list(enumerate_lineups(self.pool(),'fd',special_player_ids=ids))
