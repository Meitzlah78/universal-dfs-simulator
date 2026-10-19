import itertools,unittest
import numpy as np,pandas as pd
from simmah_candidates import build_candidates,summarize_candidates,construction_sample_size,sample_construction_targets


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
    def test_classic_defense_aliases_and_missing_position_diagnostics(self):
        pool,out,roster=fixture()
        for alias in ['D','DEF','DST']:
            changed=pool.copy();changed.loc[changed.Position.eq('DST'),'Position']=alias
            result=build_candidates(changed,out,roster,target=10,rng=np.random.default_rng(4))
            self.assertEqual(len(result),10)
            self.assertTrue(set(result.DST)<=set(changed.loc[changed.Position.eq(alias),'Name']))
        changed=pool[~pool.Position.eq('TE')].copy()
        with self.assertRaisesRegex(ValueError,r'roster slot\(s\): TE'):
            build_candidates(changed,out,roster,target=10)

    def test_refinement_retains_search_diversity_with_mean_outcomes(self):
        pool,out,roster=fixture()
        result=build_candidates(pool,out,roster,target=300,salary_min=48000,salary_max=50000,
            scenario_diversity=0,rng=np.random.default_rng(15),max_proposals=512)
        self.assertEqual(len(result),300)
        slots=[slot for slot,_ in roster]
        keys={tuple(sorted(row)) for row in result[slots].itertuples(index=False,name=None)}
        self.assertEqual(len(keys),300)
        self.assertTrue(result.Salary.between(48000,50000).all())
        self.assertTrue((result['Build Simulations']==len(out)).all())
        for _,row in result.iterrows():
            self.assertAlmostEqual(row['Scenario Score'],out[[row[s] for s in slots]].mean().sum(),places=3)

    def test_diversity_uses_all_sims_at_zero_and_one_at_maximum(self):
        self.assertEqual(construction_sample_size(0,10000),10000)
        self.assertEqual(construction_sample_size(.5,10000),100)
        self.assertEqual(construction_sample_size(1,10000),1)
        counts=[construction_sample_size(v,10000) for v in np.linspace(0,1,21)]
        self.assertEqual(counts,sorted(counts,reverse=True))

    def test_uniform_sample_averages_preserve_complete_rows_and_reduce_variance(self):
        values=np.column_stack([np.arange(1000),1000-np.arange(1000)]).astype(float)
        original=values.copy()
        all_sims,_=sample_construction_targets(values,1000,256,np.random.default_rng(2))
        single,ids=sample_construction_targets(values,1,256,np.random.default_rng(2))
        middle,_=sample_construction_targets(values,100,256,np.random.default_rng(2))
        np.testing.assert_allclose(all_sims,np.broadcast_to(values.mean(axis=0),(256,2)))
        np.testing.assert_array_equal(single,values[ids])
        np.testing.assert_allclose(middle.sum(axis=1),1000)
        self.assertLess(middle[:,0].std(),single[:,0].std())
        np.testing.assert_array_equal(values,original)
        # Averaging two complete rows without replacement must use both.
        pair,_=sample_construction_targets(values[:2],2,5,np.random.default_rng(8))
        np.testing.assert_allclose(pair,np.broadcast_to(values[:2].mean(axis=0),(5,2)))

    def test_diversity_reaches_full_roster_and_single_game_builds(self):
        pool,out,roster=fixture()
        for value in (0,.5,1):
            result=build_candidates(pool,out,roster,target=20,scenario_diversity=value,rng=np.random.default_rng(7))
            self.assertEqual(len(result),20)
            expected=construction_sample_size(value,len(out))
            self.assertTrue((result['Build Simulations']==expected).all())
            self.assertEqual(result.attrs['construction_simulations_per_candidate'],expected)
            if value==0:
                self.assertTrue(result['Build Scenario'].isna().all())
                for _,row in result.iterrows():
                    self.assertAlmostEqual(row['Scenario Score'],out[[row[s] for s,_ in roster]].mean().sum(),places=3)
        pool=pool.iloc[:24].copy();out=out[pool.Name]
        roster=[('Captain',set())]+[(f'Flex{i}',set()) for i in range(1,6)]
        for value in (0,1):
            result=build_candidates(pool,out,roster,target=20,scenario_diversity=value,
                                    multipliers=[1.5,1,1,1,1,1],rng=np.random.default_rng(8))
            self.assertGreater(len(result),0)
            self.assertLessEqual(len(result),20)
            if value==1:self.assertEqual(len(result),20)
            if value==0:
                for _,row in result.iterrows():
                    expected=1.5*out[row['Captain']].mean()+out[[row[f'Flex{i}'] for i in range(1,6)]].mean().sum()
                    self.assertAlmostEqual(row['Scenario Score'],expected,places=3)
            self.assertEqual(result.attrs['scenario_diversity'],value)

    def test_rejects_invalid_diversity(self):
        for value in (-.1,1.1,np.nan):
            with self.assertRaises(ValueError):construction_sample_size(value,3)

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

    def test_seeded_double_stack_bringback_keeps_locks_and_unique_rosters(self):
        pool,out,roster=fixture();meta=pool.set_index('Name')
        def valid(row):
            qb=meta.loc[row['QB']];names=[row[s] for s,_ in roster if s!='QB']
            selected=meta.loc[names]
            catches=((selected.Team==qb.Team)&selected.Position.isin(['WR','TE'])).sum()
            bringback=((selected.Team==qb.Opponent)&selected.Position.isin(['RB','WR','TE'])).any()
            return catches==2 and bringback
        result=build_candidates(pool,out,roster,target=300,salary_min=47000,salary_max=50000,
            locks=['p0','p1'],primary_stacks=[(2,True)],validator=valid,
            rng=np.random.default_rng(8),max_proposals=10000)
        self.assertEqual(len(result),300)
        self.assertTrue(result.attrs['stack_seeded'])
        for row in result.to_dict('records'):
            self.assertTrue(valid(row))
            names=[row[s] for s,_ in roster]
            self.assertEqual(len(set(names)),9)
            self.assertIn('p0',names);self.assertIn('p1',names)
            self.assertTrue(47000<=row['Salary']<=50000)

    def test_invalid_outcome_matrix_and_infeasible_locks(self):
        pool,out,roster=fixture()
        with self.assertRaises(ValueError):build_candidates(pool,out.drop(columns='p0'),roster,target=1)
        with self.assertRaises(ValueError):build_candidates(pool,out,roster,locks=['missing'],target=1)
        result=build_candidates(pool,out,roster,target=10,salary_max=1,max_proposals=256)
        self.assertTrue(result.empty)


if __name__=='__main__':unittest.main()
