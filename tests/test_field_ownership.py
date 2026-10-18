import unittest
import numpy as np
import pandas as pd
from simmah_field_ownership import calibrate_field_ownership, has_ownership_targets


def fixture():
    rng=np.random.default_rng(19)
    names=np.array([f'P{i}' for i in range(60)])
    score=rng.random((20000,60));score[:,0]*=.25
    picks=np.argsort(score,axis=1)[:,:9]
    field=pd.DataFrame(names[picks],columns=[f'S{i}' for i in range(9)])
    field['Salary']=np.where(np.arange(len(field))%2,60000,59500)
    field['ProjectedPoints']=np.arange(len(field))*.001
    field['Proposal ID']=np.arange(len(field))
    pool=pd.DataFrame({'Name':names,'Projected Ownership':np.full(60,15.)})
    return field,pool,list(field.columns[:9])


class FieldOwnershipTests(unittest.TestCase):
    def test_final_ownership_and_salary_mix_without_reusing_proposals(self):
        field,pool,slots=fixture()
        before=(field[slots]=='P0').any(axis=1).mean()*100
        self.assertGreater(before,40)
        result,report=calibrate_field_ownership(field,pool,slots,2000,rng=np.random.default_rng(8))
        self.assertEqual(len(result),2000)
        self.assertEqual(result['Proposal ID'].nunique(),2000)
        self.assertEqual(result.Salary.value_counts().to_dict(),{59500:1000,60000:1000})
        self.assertLess(report['Difference (pp)'].abs().mean(),1)
        self.assertLess(report['Difference (pp)'].abs().max(),3)
        # Every full row including its score and salary is from an original
        # independent legal proposal; fitting never edits lineup contents.
        pd.testing.assert_frame_equal(result,field.set_index('Proposal ID',drop=False).loc[result['Proposal ID']].reset_index(drop=True),check_flags=False)

    def test_zero_and_unlisted_targets(self):
        field,pool,slots=fixture();pool.loc[0,'Projected Ownership']=0;pool.loc[1,'Projected Ownership']=np.nan
        result,report=calibrate_field_ownership(field,pool,slots,1000,rng=np.random.default_rng(3))
        self.assertFalse((result[slots]=='P0').any().any())
        self.assertNotIn('P1',report.Name.tolist())
        self.assertTrue(result.attrs['ownership_calibration']['zero_enforced'])

    def test_missing_support_reported_not_fabricated(self):
        field,pool,slots=fixture()
        pool.loc[len(pool)]={'Name':'Absent','Projected Ownership':25}
        result,report=calibrate_field_ownership(field,pool,slots,1000,rng=np.random.default_rng(3))
        row=report[report.Name=='Absent'].iloc[0]
        self.assertFalse(row['Proposal Supported'])
        self.assertEqual(row['Final Field Own %'],0)
        self.assertGreaterEqual(result.attrs['ownership_calibration']['max_error_pp'],25)

    def test_no_external_targets_preserves_baseline(self):
        field,pool,slots=fixture();pool=pool.drop(columns='Projected Ownership')
        self.assertFalse(has_ownership_targets(pool))
        result,report=calibrate_field_ownership(field,pool,slots,1000)
        pd.testing.assert_frame_equal(result,field.iloc[:1000])
        self.assertTrue(report.empty)

    def test_repeatable_and_exact_nonround_target(self):
        field,pool,slots=fixture()
        a,ar=calibrate_field_ownership(field,pool,slots,1001,rng=np.random.default_rng(4))
        b,br=calibrate_field_ownership(field,pool,slots,1001,rng=np.random.default_rng(4))
        self.assertEqual(len(a),1001)
        pd.testing.assert_frame_equal(a,b);pd.testing.assert_frame_equal(ar,br)

if __name__=='__main__':unittest.main()

class FullRosterCalibrationIntegrationTests(unittest.TestCase):
    def test_dk_and_fd_keep_site_legality_and_exact_final_counts(self):
        from test_candidates import fixture as candidate_fixture
        from simmah_classic_field import build_full_roster_field,classic_tournament_mask
        for site in ['DraftKings','FanDuel']:
            pool,_,roster=candidate_fixture('FD' if site=='FanDuel' else 'DK')
            pool['Projection']=pool.Salary/500
            slots=[s for s,_ in roster]
            proposals=build_full_roster_field(pool,np.ones(len(pool)),slots,5000,rng=np.random.default_rng(8),platform=site)
            # A deliberately tilted marginal distribution, supported by these
            # proposals, provides a feasible external-target regression.
            weights=np.where(proposals[slots].eq(pool.Name.iloc[0]).any(axis=1),.4,1.)
            weights/=weights.sum()
            pool['Projected Ownership']=[100*weights[proposals[slots].eq(name).any(axis=1)].sum() for name in pool.Name]
            result,report=calibrate_field_ownership(proposals,pool,slots,1000,rng=np.random.default_rng(9))
            self.assertEqual(len(result),1000)
            index={name:i for i,name in enumerate(pool.Name)}
            picks=np.array([[index[name] for name in row] for row in result[slots].itertuples(index=False,name=None)])
            self.assertTrue(classic_tournament_mask(picks,pool.Team,pool.Position,max_from_team=4 if site=='FanDuel' else 8).all())
            floor,cap=(59000,60000) if site=='FanDuel' else (48500,50000)
            self.assertTrue(result.Salary.between(floor,cap).all())
            self.assertLess(report['Difference (pp)'].abs().mean(),1.2)
