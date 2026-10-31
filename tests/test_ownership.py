import unittest
from datetime import datetime, timezone
import pandas as pd
from simmah_ownership import parse_sharksnip, apply_sharksnip

NOW = datetime(2026, 10, 18, 4, tzinfo=timezone.utc)
HTML = '''DraftKings classic generatedAt:"2026-10-18T03:00:00Z" draftGroupId:"123" startsAt:"2026-10-18T17:00:00Z" gameIds:["2026_06_BUF_LV"]
<table data-testid="picks-dfs-table"><tr><th>Player</th><th>Pos</th><th>Team</th><th>Opp</th><th>DK Salary</th><th>Proj</th><th>Value (pts/$1K)</th><th>Own% (modelled)</th></tr><tr><td>Josh Allen</td><td>QB</td><td>BUF</td><td>LV</td><td>$7,500</td><td>22</td><td>3</td><td>21.8%</td></tr></table>'''

def pool():
    return pd.DataFrame([dict(Name='Josh Allen', Team='BUF', Opponent='LV', Position='QB', Salary=7500, MeanPoints=22)])

class OwnershipTests(unittest.TestCase):
    def test_match_and_provenance(self):
        p, note = apply_sharksnip(pool(), HTML, NOW)
        self.assertEqual(p['Projected Ownership'].iloc[0], 21.8)
        self.assertIn('experimental', p['Ownership Source'].iloc[0])

    def test_uploaded_zero_wins(self):
        p = pool(); p['Projected Ownership'] = 0
        result, note = apply_sharksnip(p, 'broken', NOW)
        self.assertEqual(result['Projected Ownership'].iloc[0], 0)

    def test_stale_started_and_schema_rejected(self):
        for html in [HTML.replace('generatedAt:"2026-10-18', 'generatedAt:"2026-10-16'), HTML.replace('17:00:00Z', '01:00:00Z'), HTML.replace('Own% (modelled)', 'Own')]:
            with self.assertRaises(ValueError):
                parse_sharksnip(html, NOW)

    def test_wrong_slate_and_salary_rejected(self):
        for col, value in [('Opponent', 'KC'), ('Salary', 7400)]:
            p = pool(); p[col] = value
            with self.assertRaises(ValueError):
                apply_sharksnip(p, HTML, NOW)

    def test_impossible_position_totals_rejected(self):
        p = pd.concat([pool()] * 4, ignore_index=True)
        html = HTML.replace('21.8%', '90.0%')
        with self.assertRaisesRegex(ValueError, 'roster capacity'):
            apply_sharksnip(p, html, NOW)
