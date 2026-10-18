import unittest
from datetime import datetime, timezone
import pandas as pd
from simmah_footballguys import DEFENSES, apply_footballguys, parse_footballguys
NOW = datetime(2026,10,18,15,55,tzinfo=timezone.utc)


def fixture(site='draftkings'):
    source = f'<SELECT NAME="site"><OPTION VALUE="{site}" selected="selected">Site</SELECT><SELECT NAME="week"><OPTION VALUE="6" selected>6</SELECT>Last updated <b>Sun, Oct 18 at 12:42 PM GMT</b>'
    rows=[]
    for pos,total in [('qb',100),('rb',230),('wr',320),('te',140)]:
        source += f'<table id="data-{pos}">'
        for i in range(15):
            name=f'Player {pos} {i}'
            source += f'<tr><td class="la">{name}</td><td>{total/15}%</td></tr>'
            rows.append(dict(Name=name,Position=pos.upper(),Team=list(DEFENSES.values())[i%20],MeanPoints=10))
        source += '</table>'
    source += '<table id="data-td">'
    for name,team in list(DEFENSES.items())[:20]:
        source += f'<tr><td class="la">{name}</td><td>5%</td></tr>'
        rows.append(dict(Name=team,Position='D',Team=team,MeanPoints=8))
    source += '</table>'
    return source,pd.DataFrame(rows)


class FootballguysTests(unittest.TestCase):
    def test_both_sites_and_defenses(self):
        for site in ['draftkings','fanduel']:
            html,pool=fixture(site)
            result,note=apply_footballguys(pool,html,site,NOW)
            self.assertTrue(result['Projected Ownership'].notna().all())
            self.assertEqual(result.iloc[-1]['Projected Ownership'],5)
            self.assertIn('80/80',note)

    def test_missing_unknown_not_zero(self):
        html,pool=fixture()
        pool.loc[0,'Name']='Unlisted player'
        result,_=apply_footballguys(pool,html,'draftkings',NOW)
        self.assertTrue(pd.isna(result.iloc[0]['Projected Ownership']))
        self.assertGreater(result.iloc[0]['Ownership Selection Weight'],0)
        self.assertIn('fallback',result.iloc[0]['Ownership Source'])

    def test_uploaded_zero_preserved(self):
        _,pool=fixture();pool['Projected Ownership']=0
        result,_=apply_footballguys(pool,'broken','draftkings',NOW)
        self.assertTrue((result['Projected Ownership']==0).all())

    def test_bad_metadata_capacity_and_slate_rejected(self):
        html,pool=fixture()
        for bad in [html.replace('draftkings','fanduel'),html.replace('Oct 18','Oct 11'),html.replace('5%</td>','150%</td>'),html.replace('data-te','data-unknown')]:
            with self.assertRaises(ValueError):parse_footballguys(bad,'draftkings',NOW)
        with self.assertRaises(ValueError):
            apply_footballguys(pool[pool.Team!='ARI'],html,'draftkings',NOW)
        with self.assertRaises(ValueError):
            parse_footballguys(html,'draftkings',datetime(2026,10,19,12,tzinfo=timezone.utc))

    def test_duplicate_and_suffix(self):
        from simmah_footballguys import name_key
        self.assertEqual(name_key('Kenneth Walker III'),name_key('Kenneth Walker'))
        html,_=fixture()
        with self.assertRaises(ValueError):parse_footballguys(html.replace('Player qb 1<','Player qb 0<'),'draftkings',NOW)

if __name__=='__main__':unittest.main()

class AppOwnershipWiringTests(unittest.TestCase):
    def test_field_weights_prefer_explicit_fallback_without_filling_projection_column(self):
        import ast
        from pathlib import Path
        import numpy as np
        source=Path('dfs_app.py').read_text()
        tree=ast.parse(source)
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='opponent_field_selection_weights')
        env={'pd':pd,'np':np}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<weights>','exec'),env)
        pool=pd.DataFrame({'Projected Ownership':[25,float('nan')],'Ownership Selection Weight':[25,2]})
        np.testing.assert_equal(env[fn.name](pool,[10,5]),[25,2])
        self.assertIn('if lineup_mode == "Full Roster":\n            fd_pool = attach_main_slate_ownership',source)
        self.assertIn('pool = attach_main_slate_ownership(pool, "draftkings")',source)
