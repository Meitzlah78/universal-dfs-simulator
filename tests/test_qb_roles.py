import unittest
import numpy as np
import pandas as pd
from simmah_qb_roles import quarterback_conflicts,resolve_quarterbacks
from simmah_nfl_engine import simulate_stat_lines
from test_nfl_engine import fixture

class QuarterbackRoleTests(unittest.TestCase):
    def ambiguous(self):
        pool,roles=fixture()
        backup=pool[pool.Name.eq('AQB')].copy();backup['Name']='A alternate';backup['Projection']=14.
        return pd.concat([pool,backup],ignore_index=True),roles

    def test_highest_projection_is_not_silently_assumed_to_start(self):
        pool,roles=self.ambiguous()
        with self.assertRaisesRegex(ValueError,'Multiple projected quarterbacks for A'):
            simulate_stat_lines(pool,roles,np.random.default_rng(1),32)
        with self.assertRaisesRegex(ValueError,'Confirm starting QB for A'):
            resolve_quarterbacks(pool,{})

    def test_confirmed_lower_projection_qb_gets_shared_passing_production(self):
        pool,roles=self.ambiguous();resolved=resolve_quarterbacks(pool,{'A':'A alternate'})
        self.assertNotIn('AQB',set(resolved.Name));self.assertIn('BQB',set(resolved.Name))
        for site in ['DraftKings','FanDuel']:
            stats=simulate_stat_lines(resolved,roles,np.random.default_rng(17),256,scoring_platform=site)
            self.assertGreater(stats['A alternate']['passing_yards'].mean(),0)
            np.testing.assert_allclose(stats['A alternate']['passing_yards'],
                sum(stats['A'+p]['receiving_yards'] for p in ['RB','WR','TE']),atol=.001)
        self.assertEqual(quarterback_conflicts(resolved),{})
        self.assertIn('AQB',set(pool.Name))

    def test_duplicate_rows_and_team_aliases(self):
        pool,roles=self.ambiguous();pool.loc[pool.Team.eq('A'),'Team']='LA'
        pool.loc[pool.Name.eq('A alternate'),'Team']='LAR'
        self.assertEqual(quarterback_conflicts(pool),{'LAR':['A alternate','AQB']})
        resolved=resolve_quarterbacks(pool,{'LAR':'A alternate'})
        self.assertNotIn('AQB',set(resolved.Name))
        self.assertEqual(quarterback_conflicts(pd.concat([resolved,resolved])),{})

    def test_app_choices_apply_in_all_formats_and_invalidate_only_derived_data(self):
        import ast
        from pathlib import Path
        from types import SimpleNamespace
        root=ast.parse(Path('dfs_app.py').read_text())
        helper=next(n for n in root.body if isinstance(n,ast.FunctionDef) and n.name=='resolve_quarterback_roles_for_build')
        pool,_=self.ambiguous()
        for format_label in ['DraftKings Classic','DraftKings Showdown','FanDuel Full Roster','FanDuel Single Game']:
            state={'simulation_df':'stale','saved_builds_by_slate':{'old':'stale'},'uploaded_file':'preserve'}
            st=SimpleNamespace(session_state=state,warning=lambda *a:None,caption=lambda *a:None,
                selectbox=lambda *a,**kw:'A alternate')
            ns={'st':st}
            exec(compile(ast.Module(body=[helper],type_ignores=[]),'qb-ui','exec'),ns)
            result=ns[helper.name](pool,format_label)
            self.assertNotIn('AQB',set(result.Name))
            self.assertNotIn('simulation_df',state)
            self.assertNotIn('saved_builds_by_slate',state)
            self.assertEqual(state['uploaded_file'],'preserve')
            state['simulation_df']='fresh'
            ns[helper.name](pool,format_label)
            self.assertEqual(state['simulation_df'],'fresh')
