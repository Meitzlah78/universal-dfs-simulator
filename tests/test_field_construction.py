import unittest
import numpy as np
import pandas as pd
from simmah_field_construction import learned_construction_distribution,construction_labels,construction_quotas
from simmah_classic_field import build_full_roster_field

class LearnedConstructionTest(unittest.TestCase):
    def test_profiles_are_averaged_per_contest(self):
        a={'joint_stack_bringback':{'counts':[100,0,0,0,0,0]}}
        b={'joint_stack_bringback':{'counts':[0,10000,0,0,0,0]}}
        self.assertEqual(learned_construction_distribution([a,b]),[.5,.5,0,0,0,0])
        self.assertIsNone(learned_construction_distribution([{}]))

    def test_both_sites_match_joint_mix_and_preserve_it_during_ownership_fit(self):
        from test_candidates import fixture
        from simmah_field_ownership import calibrate_field_ownership
        for site in ['DraftKings','FanDuel']:
            pool,_,roster=fixture('FD' if site=='FanDuel' else 'DK')
            pool['Projection']=pool.Salary/500
            slots=[s for s,_ in roster];mix=[.25,.05,.30,.10,.20,.10]
            field=build_full_roster_field(pool,np.ones(len(pool)),slots,2000,
                platform=site,rng=np.random.default_rng(31),construction_distribution=mix)
            counts=np.bincount(field['Construction Group'],minlength=6)
            np.testing.assert_array_equal(counts,np.array(mix)*2000)
            from simmah_contest_history import features_from_lineups,summarize,calibrate_field,name_key
            metadata={name_key(r['Name']):r for r in pool.to_dict('records')}
            features=features_from_lineups([list(zip(slots,r)) for r in field[slots].values],metadata)
            profile={'id':'fixture','format':'DK_CLASSIC' if site=='DraftKings' else 'FD_FULL',
                'lineups':2000,'features':summarize(features)}
            historical,note=calibrate_field(field,pool,slots,[profile],1500,np.random.default_rng(8))
            self.assertTrue(note['applied'])
            np.testing.assert_array_equal(np.bincount(historical['Construction Group'],minlength=6),np.array(mix)*1500)
            # Ownership targets are intentionally neutral, and cannot destroy construction quotas.
            pool['Projected Ownership']=900/len(pool)
            selected,report=calibrate_field_ownership(historical,pool,slots,1000,np.random.default_rng(72))
            np.testing.assert_array_equal(np.bincount(selected['Construction Group'],minlength=6),np.array(mix)*1000)
            self.assertTrue(selected.Salary.between(48500 if site=='DraftKings' else 59000,50000 if site=='DraftKings' else 60000).all())
            for row in selected[slots].values:self.assertEqual(len(set(row)),9)

    def test_ingest_records_joint_counts_only_with_verified_metadata(self):
        from simmah_contest_history import ingest_frames,name_key
        roster=[('QB','Quarterback'),('RB','Runner One'),('RB','Runner Two'),
                ('WR','Receiver One'),('WR','Receiver Two'),('WR','Receiver Three'),
                ('TE','Tight End'),('FLEX','Flex Player'),('DST','Defense')]
        frame=pd.DataFrame({'Rank':[1],'EntryId':['123'],'Lineup':[' '.join(s+' '+n for s,n in roster)]})
        meta={name_key(n):{'Team':'A' if s in {'QB','WR'} else 'B','Opponent':'B',
            'Position':'WR' if s=='FLEX' else s,'Salary':5000} for s,n in roster}
        profile=ingest_frames([frame],'digest',platform='DraftKings',mode='Classic',metadata=meta)[0]
        self.assertEqual(profile['joint_stack_bringback']['counts'],[0,0,0,0,0,1])
        self.assertNotIn('joint_stack_bringback',ingest_frames([frame],'digest',platform='DraftKings',mode='Classic')[0])

    def test_unsupported_mix_fails_instead_of_silently_substituting(self):
        field=pd.DataFrame({'Salary':[50000]*10,'Construction Group':[0]*10})
        field.attrs['construction_distribution']=[0,0,1,0,0,0]
        with self.assertRaisesRegex(ValueError,'supported'):construction_quotas(field,5)
