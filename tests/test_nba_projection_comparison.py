import copy
import json
import unittest
import pandas as pd
from simmah_nba_projection_comparison import parse_lineups, freeze_comparison, grade_comparisons


class ProjectionComparisonTests(unittest.TestCase):
    def source(self, **changes):
        row = dict(playerId='123', gameId='456', name='Player A', team='NYK', opponent='PHI',
                   minutes=25, overallProjection=999, fanduelProjection=30, draftkingsProjection=32)
        row.update(changes)
        return row

    def html(self, rows):
        return '<script type="application/json" data-sdw-ssr-state>' + json.dumps({'v': 1, 'data': {'rows': rows}}) + '</script>'

    def frozen(self, **changes):
        pool = pd.DataFrame([{'Player ID': 'rw123', 'Name': 'Player A', 'Team': 'NY', 'Opponent': 'PHI'}])
        args = dict(platform='FanDuel', day='2026-10-24', rotowire_fetched_at='2026-10-24T17:00:00-04:00',
                    lineups_fetched_at='2026-10-24T17:00:00-04:00', now='2026-10-24T17:01:00-04:00')
        args.update(changes)
        return freeze_comparison(pool, {('player a', 'NY'): 28},
            {('player a', 'NY'): {'Game Start': '2026-10-24T19:00:00-04:00', 'Projected Minutes': 24}},
            parse_lineups(self.html([self.source()])), **args)

    def actual(self, **changes):
        row = {'date': '2026-10-24', 'platform': 'FanDuel', 'Name': 'Player A', 'Team': 'NY', 'Opponent': 'PHI',
               'Game Status': 'FINAL', 'Fantasy Points': 26, 'Issue': ''}
        row.update(changes)
        return row

    def test_site_scoring_is_not_overall_and_zero_is_not_missing(self):
        parsed = parse_lineups(self.html([self.source(fanduelProjection=0, minutes=None)]))[0]
        self.assertEqual(parsed['FanDuel'], 0)
        self.assertEqual(parsed['DraftKings'], 32)
        self.assertIsNone(parsed['minutes'])
        self.assertNotIn('overallProjection', parsed)
        dk = self.frozen(platform='DraftKings')
        self.assertEqual(dk['players'][0]['Lineups Points'], 32)

    def test_duplicate_rows_and_unavailable_page_rejected(self):
        for html in [self.html([self.source(), self.source()]), '<html>Access unavailable</html>']:
            with self.assertRaises(ValueError):parse_lineups(html)

    def test_before_tip_date_and_freshness_guards(self):
        self.assertEqual(len(self.frozen()['players']), 1)
        self.assertEqual(self.frozen(now='2026-10-24T19:00:00-04:00',
            rotowire_fetched_at='2026-10-24T18:59:00-04:00', lineups_fetched_at='2026-10-24T18:59:00-04:00')['players'], [])
        for changes in [{'now': '2026-10-25T17:01:00-04:00'},
                        {'rotowire_fetched_at': '2026-10-24T16:00:00-04:00'},
                        {'lineups_fetched_at': '2026-10-24T18:00:00-04:00'}]:
            with self.assertRaises(ValueError):self.frozen(**changes)

    def test_last_pretip_snapshot_only_and_common_sample(self):
        early, late = self.frozen(), self.frozen(now='2026-10-24T17:02:00-04:00')
        late['players'][0]['RotoWire Points'] = 27
        report = grade_comparisons([early, late, late], [self.actual()])
        self.assertEqual(len(report['players']), 1)
        fd = [row for row in report['summary'] if row['platform'] == 'FanDuel']
        self.assertEqual([r['players'] for r in fd], [1, 1])
        self.assertEqual([r['mae'] for r in fd], [1, 4])
        missing = copy.deepcopy(late);missing['players'][0]['Lineups Points'] = None
        result = grade_comparisons([missing], [self.actual()])
        self.assertEqual(result['coverage']['FanDuel']['final_actuals'], 1)
        self.assertTrue(all(row['players'] == 0 for row in result['summary']))

    def test_live_unmatched_wrong_site_and_wrong_day_are_not_zero(self):
        for actuals in [[], [self.actual(**{'Game Status': 'LIVE'})], [self.actual(platform='DraftKings')],
                        [self.actual(date='2026-10-23')], [self.actual(**{'Fantasy Points': None})]]:
            report = grade_comparisons([self.frozen()], actuals)
            self.assertEqual(report['coverage']['FanDuel']['paired'], 0)
            self.assertIsNone(report['players'][0]['Actual Points'])
        for score in [0, -2]:
            report = grade_comparisons([self.frozen()], [self.actual(**{'Fantasy Points': score})])
            self.assertEqual(report['coverage']['FanDuel']['paired'], 1)
            self.assertEqual(report['players'][0]['Actual Points'], score)

    def test_post_tip_reconstruction_and_ambiguous_actuals_rejected(self):
        bad = self.frozen();bad['captured_at'] = '2026-10-24T19:01:00-04:00'
        with self.assertRaises(ValueError):grade_comparisons([bad], [self.actual()])
        with self.assertRaises(ValueError):grade_comparisons([self.frozen()], [self.actual(), self.actual()])


if __name__ == '__main__':unittest.main()
