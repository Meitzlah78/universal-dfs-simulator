import unittest
import numpy as np
from simmah_nba_contest import evaluate_candidates


class RankHistogramTests(unittest.TestCase):
    def test_weighted_ranks_match_expanded_field(self):
        rng=np.random.default_rng(91)
        for slots,ticks in ((8,4),(9,10)):
            candidates=np.array([rng.choice(15,slots,replace=False) for _ in range(12)])
            field=np.array([rng.choice(15,slots,replace=False) for _ in range(15)])
            copies=rng.integers(1,5,len(field))
            outcomes=rng.integers(-4,8,(20,15))/ticks
            outcomes[0]=0  # All tied, including compressed duplicates.
            for factor in (1,100000):  # Histogram and bounded-memory sort paths.
                x=outcomes*factor
                prize=np.maximum(0,20-np.arange(int(copies.sum())+1))
                report=evaluate_candidates(x,candidates,field,prize,1,
                    construction_seed=1,evaluation_seed=2,field_copies=copies,score_ticks=ticks)
                actual=[]
                for lineup in candidates:
                    wins=[]
                    for scenario in x:
                        score=round(scenario[lineup].sum()*ticks)
                        opponents=np.repeat(np.rint(scenario[field].sum(axis=1)*ticks),copies)
                        above=int((opponents>score).sum())
                        ties=int((opponents==score).sum())+1
                        wins.append(prize[above:above+ties].mean())
                    actual.append(np.mean(wins))
                np.testing.assert_allclose(report['Expected Prize ($)'],actual,rtol=0,atol=1e-12)
