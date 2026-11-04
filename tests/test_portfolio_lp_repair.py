import unittest
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
import pandas as pd
from scipy.sparse import csc_matrix,vstack
from simmah_portfolio_selection import select_portfolio,_lp_supported_repair

class LPRepairTests(unittest.TestCase):
    def test_large_trap_recovers_even_when_full_integer_searches_timeout(self):
        rows=[]
        for i in range(600):
            a,b,quality=[('A','B',1.),('A','C',.9),('B','D',.8)][i%3]
            rows.append({'S0':a,'S1':b,'S2':'Unique'+str(i),'Top1':quality})
        frame=pd.DataFrame(rows)
        controls={name:{'Max Exposure %':50} for name in 'ABCD'}
        with patch('scipy.optimize.milp',return_value=SimpleNamespace(status=1,x=None)):
            chosen=select_portfolio(frame,['S0','S1','S2'],20,'Top1',controls,diversity=0)
        self.assertEqual(len(chosen),20)
        self.assertEqual(chosen.S2.nunique(),20)
        counts=chosen[['S0','S1']].stack().value_counts()
        self.assertTrue(counts.le(10).all())
        self.assertEqual(chosen.attrs['effective_auto_cap_pct'],100)

    def test_fractional_relaxation_is_repaired_not_rounded_into_a_portfolio(self):
        incidence=np.array([[1,1,0],[1,0,1],[0,1,1],[0,0,0]])
        matrix=vstack([csc_matrix(np.ones((1,4))),csc_matrix(incidence.T)],format='csc')
        chosen=_lp_supported_repair(matrix,np.zeros(3),np.ones(3),2,np.array([-1.,-1.,-1.,0.]),np.ones(4,bool))
        self.assertEqual(len(chosen),2)
        self.assertIn(3,chosen)
        self.assertTrue((incidence[chosen].sum(axis=0)<=1).all())

    def test_infeasible_fractional_support_does_not_prove_full_infeasibility(self):
        triangle=np.array([[1,1,0],[1,0,1],[0,1,1]])
        incidence=np.zeros((7,6),int);incidence[:3,:3]=triangle;incidence[3:6,3:]=triangle
        matrix=vstack([csc_matrix(np.ones((1,7))),csc_matrix(incidence.T)],format='csc')
        result=_lp_supported_repair(matrix,np.zeros(6),np.ones(6),3,np.r_[-np.ones(6),0.],np.ones(7,bool))
        self.assertIsNone(result)
        self.assertTrue((incidence[[0,3,6]].sum(axis=0)<=1).all())

    def test_relaxation_timeout_returns_to_full_search(self):
        matrix=csc_matrix(np.ones((2,3)))
        with patch('scipy.optimize.linprog',return_value=SimpleNamespace(x=None,status=1)):
            self.assertIsNone(_lp_supported_repair(matrix,np.zeros(1),np.ones(1),1,np.zeros(3),np.ones(3,bool)))

    def test_invalid_integer_incumbent_is_never_returned(self):
        incidence=np.array([[1,1,0],[1,0,1],[0,1,1],[0,0,0]])
        matrix=vstack([csc_matrix(np.ones((1,4))),csc_matrix(incidence.T)],format='csc')
        with patch('scipy.optimize.milp',return_value=SimpleNamespace(x=np.ones(4),status=1)):
            self.assertIsNone(_lp_supported_repair(matrix,np.zeros(3),np.ones(3),2,np.array([-1.,-1.,-1.,0.]),np.ones(4,bool)))

if __name__=='__main__':unittest.main()
