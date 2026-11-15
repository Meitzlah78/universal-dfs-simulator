import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from simmah_nfl_event_levers_offline import read_season,fit_gain,sample_gain,fit_fourth,predict_fourth,baseline_fourth,gains,fourth_rows,evaluate_gains,evaluate_fourth,fit_rushing_body


def rows(kind='run',n=240):
    return pd.DataFrame([{'season':2022 if i%2 else 2023,'game_id':f'g{i//10}','play_id':i,
        'play_type':'run' if kind=='run' else 'pass','qtr':1,'down':4,'ydstogo':1,
        'yardline_100':40.,'game_seconds_remaining':2400.,'score_differential':0,
        'qb_kneel':0,'qb_spike':0,'qb_scramble':0,'two_point_attempt':0,'extra_point_attempt':0,
        'complete_pass':1,'yards_gained':2 if i%10 else 40,'rush_touchdown':int(kind=='run' and i%10==0),
        'pass_touchdown':int(kind!='run' and i%10==0)} for i in range(n)])


class EventLeverTests(unittest.TestCase):
    def test_short_body_preserves_every_outside_probability(self):
        f=rows();m=fit_gain(f,'run');new=fit_rushing_body(m,f)
        outside=~np.isin(np.asarray(m['support']),[1,2,3,4,5,6])
        np.testing.assert_array_equal(np.asarray(m['probabilities'])[outside],np.asarray(new['probabilities'])[outside])
        c=new['body_calibration'];self.assertAlmostEqual(c['expected_after'],c['target_observed_training_ypc'],places=8)
        self.assertAlmostEqual(sum(new['probabilities']),1)
    def test_short_body_rejects_tuning_data(self):
        f=rows();m=fit_gain(f,'run');f['season']=2024
        with self.assertRaises(ValueError):fit_rushing_body(m,f)
    def test_locked_seasons_cannot_be_opened(self):
        with patch('simmah_nfl_event_levers_offline.pd.read_csv') as read:
            with self.assertRaisesRegex(ValueError,'Locked'):read_season('/tmp',2025)
            with self.assertRaisesRegex(ValueError,'Locked'):read_season('/tmp',2026)
            read.assert_not_called()
    def test_2024_cannot_fit_either_candidate(self):
        f=rows();f['season']=2024
        with self.assertRaises(ValueError):fit_gain(f,'run')
        with self.assertRaises(ValueError):fit_fourth(f)
    def test_2025_frame_cannot_be_evaluated(self):
        train=rows();m=fit_fourth(train);test=rows();test['season']=2025
        with self.assertRaises(ValueError):evaluate_fourth(m,test)
        with self.assertRaises(ValueError):evaluate_gains({},test)

    def test_gain_mass_and_censored_support(self):
        model=fit_gain(rows(),'run');p=np.asarray(model['probabilities']);support=np.asarray(model['support'])
        self.assertAlmostEqual(p.sum(),1)
        self.assertTrue((p>=0).all())
        self.assertGreater(p[support>=40].sum(),0)
        self.assertEqual(model['censored_touchdowns'],24)
    def test_shared_inputs_are_deterministic_and_caps_unchanged(self):
        m=fit_gain(rows(),'run');u=np.linspace(0,.99999,1000);env=np.ones(1000)
        a=sample_gain(m,u,env);b=sample_gain(m,u,env)
        np.testing.assert_array_equal(a,b)
        self.assertGreaterEqual(a.min(),-5);self.assertLessEqual(a.max(),65)
    def test_invalid_random_input_not_silently_clipped(self):
        m=fit_gain(rows(),'run')
        with self.assertRaises(ValueError):sample_gain(m,[1.],[1.])
    def test_scrambles_are_not_designed_runs(self):
        f=rows();f.loc[0,'qb_scramble']=1
        self.assertEqual(len(gains(f,'run')),len(f)-1)
    def test_knells_spikes_and_conversions_not_training_events(self):
        f=rows();f.loc[0,'qb_kneel']=1;f.loc[1,'qb_spike']=1;f.loc[2,'two_point_attempt']=1
        self.assertEqual(len(gains(f,'run')),len(f)-3)
        self.assertEqual(len(fourth_rows(f)),len(f)-3)
    def test_neutral_midfield_short_candidate_can_go(self):
        f=rows();f.loc[f.index%5==0,'play_type']='punt'
        model=fit_fourth(f);p=predict_fourth(model,f)
        self.assertTrue((p>.5).all());self.assertTrue((baseline_fourth(f)==0).all())
    def test_outcome_columns_do_not_enter_prediction(self):
        f=rows();f.loc[f.index%4==0,'play_type']='punt';m=fit_fourth(f)
        a=predict_fourth(m,f);f['yards_gained']=99;f['play_type']='field_goal';f['rush_touchdown']=1
        np.testing.assert_array_equal(a,predict_fourth(m,f))
    def test_fourth_down_state_required(self):
        f=rows();m=fit_fourth(f);f['down']=3
        with self.assertRaises(ValueError):predict_fourth(m,f)
    def test_exact_five_yard_boundary_stays_outside_inside5(self):
        f=rows();f['yardline_100']=5
        self.assertTrue((baseline_fourth(f)==0).all())
        f['yardline_100']=4
        self.assertTrue((baseline_fourth(f)==1).all())
    def test_field_censoring_never_creates_twenty_yard_plays_at_one(self):
        train=rows();models={'run':fit_gain(train,'run'),'completion':fit_gain(rows('completion'),'completion')}
        test=pd.concat([rows(),rows('completion')]);test['season']=2024;test['yardline_100']=1
        result=evaluate_gains(models,test,draws=4,seeds=(1,))
        for kind in ['run','completion']:
            self.assertEqual(result['results'][kind]['candidates']['empirical_censor_aware']['gain_20_rate'],0)

if __name__=='__main__':unittest.main()
