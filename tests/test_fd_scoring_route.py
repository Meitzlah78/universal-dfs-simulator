"""Exercise the live FD Step 4 branch with roster-only opponent tables."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
import numpy as np
import pandas as pd

class FanDuelScoringRouteTests(unittest.TestCase):
    def route(self):
        tree=ast.parse(Path('dfs_app.py').read_text())
        for node in ast.walk(tree):
            if not isinstance(node,ast.If):continue
            for i,step in enumerate(node.orelse):
                if (isinstance(step,ast.If) and isinstance(step.test,ast.Compare)
                        and isinstance(step.test.left,ast.Name) and step.test.left.id=='lineup_mode'
                        and any(isinstance(x,ast.Constant) and x.value=='Full Roster' for x in step.test.comparators)
                        and any(isinstance(x,ast.Name) and x.id=='opponent_df' for x in ast.walk(step))):
                    return compile(ast.Module(body=node.orelse[:i+1],type_ignores=[]),'live-fd-step4','exec')
        raise AssertionError('Live FD contest scoring branch not found')
    def run_route(self,mode,payouts_known=True):
        single=mode=='Single Game'
        slots=['MVP','FLEX1','FLEX2','FLEX3','FLEX4','FLEX5'] if single else ['QB','RB1','RB2','WR1','WR2','WR3','TE','FLEX','D']
        names=list('ABCDEFGHIJKL')
        # Only the special-role assignment separates the two single-game rows:
        # H at MVP beats A at MVP with the same six rostered players.
        own=['H','A','B','C','D','E'] if single else names[:9]
        opp=['A','H','B','C','D','E'] if single else names[3:12]
        user=pd.DataFrame([dict(zip(slots,own))]);field=pd.DataFrame([dict(zip(slots,opp))])
        outcomes=pd.DataFrame(np.tile(np.arange(1.,13.),(8,1)),columns=names)
        state={'fd_simulation_df_single_game':outcomes,'fd_simulation_df_full_roster':outcomes}
        spec={'field_size':2,'tiers':[(1,1,5.)],'fee':1.,'payouts_known':payouts_known}
        ns={'np':np,'pd':pd,'st':SimpleNamespace(session_state=state,caption=lambda *a:None,info=lambda *a:None),
            'user_lineups':user,'opponent_df':field,'lineup_mode':mode,'fd_slots':slots,'SIMULATION_COUNT':8,
            'add_lineup_field_ownership':lambda frame:frame,
            'full_roster_contest_parameters':lambda *a:spec,
            'fd_step4_progress':SimpleNamespace(progress=lambda *a,**kw:None)}
        exec(self.route(),ns)
        return ns['compared'],user,field
    def test_single_game_roster_only_field_scores_mvp_on_shared_outcomes(self):
        result,user,field=self.run_route('Single Game')
        self.assertNotIn('ProjectedPoints',field)
        self.assertEqual(result.iloc[0]['WinRate'],1.)
        self.assertEqual(result.iloc[0]['Expected Prize ($)'],5.)
        pd.testing.assert_frame_equal(result[user.columns],user)
    def test_full_roster_roster_only_field_uses_shared_outcomes(self):
        result,_,field=self.run_route('Full Roster')
        self.assertNotIn('ProjectedPoints',field)
        self.assertEqual(result.iloc[0]['WinRate'],0.)
        self.assertEqual(result.iloc[0]['Expected Prize ($)'],0.)
    def test_unknown_payouts_keep_finish_rates_and_hide_roi(self):
        for mode in ('Single Game','Full Roster'):
            result,_,_=self.run_route(mode,False)
            self.assertIn('Top1',result)
            self.assertNotIn('Expected ROI (%)',result)
            self.assertNotIn('Expected Prize ($)',result)

if __name__=='__main__':unittest.main()
