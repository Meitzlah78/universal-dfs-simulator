import itertools,unittest
import numpy as np,pandas as pd
from simmah_candidates import build_candidates,summarize_candidates


def fixture(site='DK'):
    rng=np.random.default_rng(4);rows=[]
    for team in range(8):
        for p,sal in [('QB',6000),('RB',6500),('RB',4200),('WR',7000),('WR',5100),('WR',3500),('TE',3900),('DST',3000)]:
            rows.append(dict(Name='p'+str(len(rows)),Position=p,Team=str(team),Opponent=str(team^1),Salary=sal+rng.integers(-5,6)*100))
    pool=pd.DataFrame(rows)
    if site=='FD':pool.Salary=(pool.Salary*1.25).astype(int)
    means=pool.Salary.to_numpy()/500
    out=pd.DataFrame(rng.normal(means,means*.55,(3000,len(pool))),columns=pool.Name)
    roster=[('QB',{'QB'}),('RB1',{'RB'}),('RB2',{'RB'}),('WR1',{'WR'}),('WR2',{'WR'}),('WR3',{'WR'}),('TE',{'TE'}),('FLEX',{'RB','WR','TE'}),('DST',{'DST'})]
    return pool,out,roster


class CandidateTest(unittest.TestCase):
    def test_both_full_roster_sites_locks_and_limits(self):
        for site,minimum,maximum in [('DK',47000,50000),('FD',57000,60000)]:
            pool,out,roster=fixture(site)
            result=build_candidates(pool,out,roster,target=120,salary_min=minimum,salary_max=maximum,locks=['p0'],rng=np.random.default_rng(5),max_from_team=4,require_both_teams=True)
            self.assertEqual(len(result),120)
            meta=pool.set_index('Name')
            keys=set()
            for row in result.to_dict('records'):
                names=[row[s] for s,_ in roster];self.assertEqual(len(names),len(set(names)))
                self.assertIn('p0',names)
                self.assertTrue(minimum<=row['Salary']<=maximum)
                self.assertLessEqual(meta.loc[names,'Team'].value_counts().max(),4)
                for (slot,allowed),name in zip(roster,names):self.assertIn(meta.loc[name,'Position'],allowed)
                self.assertAlmostEqual(row['Scenario Score'],float(out.loc[row['Build Scenario'],names].sum()),places=3)
                keys.add(tuple(sorted(names)))
            self.assertEqual(len(keys),len(result))

    def test_single_game_multiplier_and_role_eligibility(self):
        pool,out,_=fixture();pool=pool.iloc[:24].copy();pool.Salary=np.linspace(1000,11000,24).astype(int)
        pool.Team=['A' if i<12 else 'B' for i in range(24)];out=out[pool.Name]
        for first in ('Captain','MVP'):
            roster=[(first,set())]+[(f'Flex{i}',set()) for i in range(1,6)]
            result=build_candidates(pool,out,roster,target=150,multipliers=[1.5,1,1,1,1,1],special_allowed=set(pool.Name[:10]),require_both_teams=True,max_from_team=5,rng=np.random.default_rng(9))
            self.assertEqual(len(result),150)
            meta=pool.set_index('Name')
            for row in result.to_dict('records'):
                self.assertIn(row[first],set(pool.Name[:10]))
                others=[row[f'Flex{i}'] for i in range(1,6)]
                self.assertEqual(row['Salary'],round(meta.loc[row[first],'Salary']*1.5+meta.loc[others,'Salary'].sum()))
                expected=1.5*out.loc[row['Build Scenario'],row[first]]+out.loc[row['Build Scenario'],others].sum()
                self.assertAlmostEqual(row['Scenario Score'],expected,places=3)
                self.assertEqual(len(set([row[first]]+others)),6)

    def test_joint_percentiles_not_sum_of_marginals(self):
        outcomes=pd.DataFrame({'A':[100,0]*100,'B':[0,100]*100})
        frame=pd.DataFrame([{'S1':'A','S2':'B'}])
        result=summarize_candidates(frame,outcomes,['S1','S2'])
        self.assertEqual(result['SimP95'].iloc[0],100)
        self.assertEqual(result['SimMean'].iloc[0],100)
        self.assertEqual(sum(outcomes.quantile(.95)),200)

    def test_unconstrained_toy_matches_exhaustive_optimum(self):
        pool=pd.DataFrame({'Name':list('ABCDEFGH'),'Position':['WR']*8,'Team':['A']*4+['B']*4,'Salary':[1000]*8})
        outcomes=pd.DataFrame([np.arange(1,9)],columns=pool.Name)
        roster=[('Captain',set())]+[(f'Flex{i}',set()) for i in range(1,6)]
        result=build_candidates(pool,outcomes,roster,target=1,multipliers=[1.5,1,1,1,1,1],rng=np.random.default_rng(1),noise=0)
        expected=max(1.5*outcomes.loc[0,c]+outcomes.loc[0,list(flex)].sum() for c in pool.Name for flex in itertools.combinations([p for p in pool.Name if p!=c],5))
        self.assertEqual(result['Scenario Score'].iloc[0],expected)

    def test_invalid_outcome_matrix_and_infeasible_locks(self):
        pool,out,roster=fixture()
        with self.assertRaises(ValueError):build_candidates(pool,out.drop(columns='p0'),roster,target=1)
        with self.assertRaises(ValueError):build_candidates(pool,out,roster,locks=['missing'],target=1)
        result=build_candidates(pool,out,roster,target=10,salary_max=1,max_proposals=256)
        self.assertTrue(result.empty)


if __name__=='__main__':unittest.main()
