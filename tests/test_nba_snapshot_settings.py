import copy
import unittest
import numpy as np
from simmah_nba_snapshot_settings import BASELINE,FIXED,SITE_RULES,validate_settings,SnapshotContractError

class SettingsTests(unittest.TestCase):
    def fixture(self,site='fd',mode='relative popularity'):
        settings={'schema_version':'1.0','artifact_type':'initial_build','baseline_commit':BASELINE,'site':site,'slate_id':'main','slate_date':'2026-10-21',
          'pipeline':dict(simulations=10000,candidate_target=5000,field_support_target=10000,seed=83,diversity=50,salary_min=0,max_ownership_error=5,ownership_mode=mode,correlation=0,portfolio_count=20,ownership_source='fixture',excluded_indices=[0],excluded_player_ids=['0']),
          'contest':dict(id='123',entry_fee=.1,contest_entries=100,represented_opponent_entries=99),
          'site_rules':copy.deepcopy(SITE_RULES[site]),'implementation':copy.deepcopy(FIXED)}
        own=np.full(10,len(SITE_RULES[site]['slots'])*10.) if mode=='projected' else np.ones(10)
        args=dict(player_ids=list(map(str,range(10))),ownership=own,payouts=np.r_[100.,np.zeros(99)],pool_platform=SITE_RULES[site]['platform'])
        return settings,args
    def test_both_sites_both_modes(self):
        for site in ['dk','fd']:
            for mode in ['projected','relative popularity']:
                s,a=self.fixture(site,mode);before=copy.deepcopy(s);validate_settings(s,**a);self.assertEqual(s,before)
    def test_each_required_pipeline_setting(self):
        original,args=self.fixture()
        for key in original['pipeline']:
            changed=copy.deepcopy(original);del changed['pipeline'][key]
            with self.assertRaises(SnapshotContractError):validate_settings(changed,**args)
    def test_bad_values_and_unknown_keys(self):
        for key,value in [('simulations',10000.),('seed',True),('max_ownership_error',float('nan')),('correlation',101),('unexpected',1)]:
            settings,args=self.fixture();settings['pipeline'][key]=value
            with self.assertRaises(SnapshotContractError):validate_settings(settings,**args)
    def test_bad_date_exclusions_and_pinned_constants(self):
        for change in ['date','exclusion','constant','fee','count','eligibility']:
            s,a=self.fixture()
            if change=='date':s['slate_date']='2026-02-30'
            if change=='exclusion':s['pipeline']['excluded_player_ids']=['wrong']
            if change=='constant':s['implementation']['cache']['max_slates']=3
            if change=='fee':s['contest']['entry_fee']=0
            if change=='count':s['contest']['represented_opponent_entries']=98
            if change=='eligibility':s['site_rules']['eligibility'][0]=['C']
            with self.assertRaises(SnapshotContractError):validate_settings(s,**a)
    def test_payload_checks_numpy_safe(self):
        for own,prize in [(np.zeros(10),np.zeros(100)),(np.ones(9),np.zeros(100)),(np.ones(10),np.r_[0.,10.,np.zeros(98)]),(np.ones(10),np.zeros(99))]:
            s,a=self.fixture();a.update(ownership=own,payouts=prize)
            with self.assertRaises(SnapshotContractError):validate_settings(s,**a)
    def test_relative_popularity_not_forced_to_roster_total(self):
        s,a=self.fixture();validate_settings(s,**a)
        s['pipeline']['ownership_mode']='projected'
        with self.assertRaises(SnapshotContractError):validate_settings(s,**a)
    def test_pinned_rules_match_runtime(self):
        from simmah_nba_rules import rules_for
        for site,expected in SITE_RULES.items():
            actual=rules_for(platform=expected['platform'])
            actual['slots']=list(actual['slots']);actual['eligibility']=[sorted(x) for x in actual['eligibility']]
            self.assertEqual(actual,expected)
