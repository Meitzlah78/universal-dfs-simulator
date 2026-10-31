import sys
import unittest
from collections import Counter
import contextlib
import io
import shutil
import tempfile
from itertools import combinations
from pathlib import Path
import numpy as np
from scipy.special import logsumexp

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'calibration'))
from nba_canonical_dp import CanonicalGraph, StateBudgetExceeded, exact_basis, legal_roster, rules


def fixture(platform='DraftKings', legacy=False):
    slots=('PG','PG','SG','SG','SF','SF','PF','PF','C') if legacy else None
    rule=rules(platform,slots)
    pos=['PG','SG','SF','PF','C','PG/SG','SF/PF','PF/C','PG','SG','SF','PF','C']
    if legacy:pos=['PG','PG','SG','SG','SF','SF','PF','PF','C','PG/SG','SF/PF','PF/C','C']
    players=[dict(id=str(i),name='Player '+str(i),positions=tuple(p.split('/')),
                  salary=4200+100*(i%5),team=['A','B','C','D'][i%4],
                  game='A@B' if i%4<2 else 'C@D') for i,p in enumerate(pos)]
    rows=[tuple(p['id'] for p in c) for c in combinations(players,len(rule['slots'])) if legal_roster(c,rule)]
    return rule,players,rows


class CanonicalTests(unittest.TestCase):
    def test_counts_partition_and_moments_across_both_sites_and_fd_layouts(self):
        for platform,legacy in [('DraftKings',False),('FanDuel',False),('FanDuel',True)]:
            rule,players,rows=fixture(platform,legacy);coordinate={p['id']:i for i,p in enumerate(players)}
            graph=CanonicalGraph(players,rule,coordinate)
            self.assertGreater(len(rows),0);self.assertEqual(graph.count,len(rows))
            A=np.zeros((len(rows),len(players)))
            for i,row in enumerate(rows):
                for pid in row:A[i,coordinate[pid]]=1
            for scale in [0,.2,150]:
                theta=np.random.default_rng(82).normal(0,scale,len(players))
                z,mean=graph.evaluate(theta);ref=logsumexp(A@theta)
                self.assertLess(abs(z-ref),1e-10)
                np.testing.assert_allclose(mean,A.T@np.exp(A@theta-ref),atol=2e-11,rtol=0)

    def test_flexible_assignments_do_not_multiply_one_roster(self):
        rule=rules('DraftKings')
        players=[dict(id=str(i),positions=('PG','SG','SF','PF','C'),salary=1000,
                      team='A' if i<4 else 'C',game='A@B' if i<4 else 'C@D') for i in range(8)]
        graph=CanonicalGraph(players,rule)
        self.assertEqual(graph.count,1)
        self.assertAlmostEqual(graph.evaluate(np.zeros(8),False),0)

    def test_exact_basis_reconstructs_and_finds_hidden_witness_directions(self):
        rule,players,rows=fixture();graph=CanonicalGraph(players,rule)
        # Start with only one roster. The exact support extrema must expand it
        # instead of treating empirical witness dependencies as global facts.
        coordinate,T,offset,proof=exact_basis(graph,[rows[0]],players)
        self.assertGreater(proof['witness_expansions'],0)
        graph.remap(coordinate)
        for row in rows:
            mean=np.zeros(len(coordinate))
            for pid in row:
                if pid in coordinate:mean[coordinate[pid]]=1
            expected=np.array([1,*[int(p['id'] in row) for p in players]])
            np.testing.assert_array_equal(offset+T@mean,expected)

    def test_exact_min_max_and_forced_players(self):
        rule,players,rows=fixture();forced=rows[0][0]
        graph=CanonicalGraph(players,rule,forced=[forced]);valid=[r for r in rows if forced in r]
        self.assertEqual(graph.count,len(valid))
        weights={p['id']:i-5 for i,p in enumerate(players)}
        low,w=graph.extreme(weights,False);high,v=graph.extreme(weights,True)
        scores=[sum(weights[pid] for pid in r) for r in valid]
        self.assertEqual(low,min(scores));self.assertEqual(high,max(scores))
        self.assertEqual(low,sum(weights[pid] for pid in w))
        self.assertEqual(high,sum(weights[pid] for pid in v))

    def test_state_budget_never_falls_back_to_sampled_support(self):
        rule,players,rows=fixture()
        with self.assertRaises(StateBudgetExceeded):CanonicalGraph(players,rule,max_states=10)

    def test_team_and_game_limits_are_enforced(self):
        rule,players,_=fixture()
        one_game=[{**p,'game':'A@B'} for p in players]
        with self.assertRaises(ValueError):CanonicalGraph(one_game,rule)
        fd=rules('FanDuel')
        two_teams=[{**p,'team':'A' if i%2 else 'B'} for i,p in enumerate(players)]
        with self.assertRaises(ValueError):CanonicalGraph(two_teams,fd)

    @unittest.skipUnless(shutil.which('gcc'),'GCC binary128 compiler required')
    def test_complete_quad_precision_calibration_on_enumerable_fixture(self):
        from nba_pipeline import NBAOracle
        import single_game_pipeline as common
        rule,players,rows=fixture()
        observed={r:1+sum(int(pid) for pid in r)%7 for r in rows}
        counts=Counter()
        for roster,copies in observed.items():
            for pid in roster:counts[pid]+=copies
        n=sum(observed.values())
        for p in players:p['historical_count']=counts[p['id']]
        graph=CanonicalGraph(players,rule)
        coordinate,T,offset,proof=exact_basis(graph,observed,players);graph.remap(coordinate)
        oracle=NBAOracle(graph,players,coordinate,T,offset,n)
        A=np.zeros((len(rows),len(coordinate)),dtype=int)
        for i,row in enumerate(rows):
            for pid in row:
                if pid in coordinate:A[i,coordinate[pid]]=1
        scale=1/np.sqrt(oracle.b*(1-oracle.b))
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            out=Path(tmp)
            theta,fit,warm=common.fit64(oracle,out,scale)
            theta,fit,quad=common.refine_quad(oracle,theta,scale,out,graph,A,np.zeros(len(coordinate)))
        self.assertEqual(quad['status'],'verified_convergence')
        self.assertTrue(common.passed(common.metrics(oracle.evaluate(theta))))


if __name__=='__main__':unittest.main()
