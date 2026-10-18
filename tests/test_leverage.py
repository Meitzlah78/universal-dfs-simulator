import numpy as np
import pandas as pd
from simmah_leverage import add_value_columns, leverage_report


def test_value_missing_and_position_comparison():
    pool=pd.DataFrame({'Name':['A','B','C'], 'Position':['WR','WR','QB'], 'Salary':[5000,10000,0], 'Projection':[20,20,30]})
    r=add_value_columns(pool)
    assert r['Projected Pts / $1k'].iloc[:2].tolist()==[4,2]
    assert np.isnan(r['Projected Pts / $1k'].iloc[2])
    assert r['Position Value Percentile'].iloc[0]==100


def test_weighted_presence_duplicates_and_captain():
    pool=pd.DataFrame({'Name':['A','B','C'], 'Salary':[5000]*3, 'Projection':[20]*3})
    candidates=pd.DataFrame({'Captain':['A','B'], 'Flex':['C','C'], 'Top1':[.3,.1]})
    field=pd.DataFrame({'Captain':['A','A','B','B'], 'Flex':['C']*4})
    r=leverage_report(pool,candidates,field,['Captain','Flex'],'Captain').set_index('Name')
    assert r.loc['A','Sim Leverage (pp)']==25
    assert r.loc['B','Sim Leverage (pp)']==-25
    assert r.loc['C','Sim Leverage (pp)']==0
    assert r.loc['A','CPT/MVP Leverage (pp)']==25
    again=leverage_report(pool,pd.concat([candidates,candidates.iloc[:1]]),field,['Captain','Flex'],'Captain').set_index('Name')
    pd.testing.assert_frame_equal(r,again)
    empty=leverage_report(pool,None,field,['Captain','Flex'])
    assert empty['Sim Leverage (pp)'].isna().all()


def test_flex_order_and_zero_success():
    pool=pd.DataFrame({'Name':['A','B','C'], 'Salary':[5000]*3, 'Projection':[20]*3})
    c=pd.DataFrame({'F1':['A','B','A'], 'F2':['B','A','C'], 'Top1':[.1,.1,.3]})
    r=leverage_report(pool,c,c,['F1','F2'])
    assert r.attrs['evaluated_unique_candidates']==2
    c['Top1']=0
    assert leverage_report(pool,c,c,['F1','F2'])['Sim Leverage (pp)'].isna().all()
