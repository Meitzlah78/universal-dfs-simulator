"""Exercise stack semantics without launching the Streamlit app."""
import ast
from pathlib import Path
import unittest
import pandas as pd


def load_rules():
    tree = ast.parse(Path('dfs_app.py').read_text())
    names = {'FULL_ROSTER_STACK_OPTIONS', 'SECONDARY_STACK_OPTIONS',
             'ANY_STACK_OPTION', 'NO_STACK_OPTION', 'BUILD_STACK_OPTIONS', 'full_roster_stack_patterns',
             'full_roster_stack_lookup', 'full_roster_stack_matches'}
    nodes = [node for node in tree.body
             if (isinstance(node, ast.FunctionDef) and node.name in names)
             or (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets))]
    ns = {'pd': pd}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'dfs_app.py', 'exec'), ns)
    return ns


class StackRulesTest(unittest.TestCase):
    def setUp(self):
        self.ns = load_rules()
        self.options = self.ns['FULL_ROSTER_STACK_OPTIONS']
        self.secondary = self.ns['SECONDARY_STACK_OPTIONS']
        rows = [
            ('QB', 'QB', 'A', 'B'), ('WR', 'WR', 'A', 'B'),
            ('TE', 'TE', 'A', 'B'), ('WR2', 'WR', 'A', 'B'),
            ('RB', 'RB', 'A', 'B'), ('Opp', 'RB', 'B', 'A'),
            ('DST', 'DST', 'A', 'B'), ('OtherD', 'D', 'C', 'D'),
            ('MiniA', 'WR', 'C', 'D'), ('MiniB', 'RB', 'D', 'C'),
            ('Unrelated', 'WR', 'E', 'F'),
        ]
        self.pool = pd.DataFrame(rows, columns=['Name', 'Position', 'Team', 'Opponent'])
        self.lookup = self.ns['full_roster_stack_lookup'](self.pool)

    def matches(self, players, rules, secondary=()):
        chosen = {'QB': 'QB', **{str(i): name for i, name in enumerate(players)}}
        return self.ns['full_roster_stack_matches'](chosen, self.pool, rules, self.lookup, secondary)

    def test_primary_counts_and_bringbacks(self):
        self.assertTrue(self.matches(['WR'], [self.options[0]]))
        self.assertFalse(self.matches(['RB', 'DST'], [self.options[0]]))
        self.assertFalse(self.matches(['WR', 'TE'], [self.options[0]]))
        self.assertTrue(self.matches(['WR', 'TE'], [self.options[1]]))
        self.assertFalse(self.matches(['WR', 'TE', 'WR2'], self.options))
        self.assertFalse(self.matches(['WR'], [self.options[2]]))
        self.assertTrue(self.matches(['WR', 'Opp'], [self.options[2]]))
        self.assertTrue(self.matches(['WR', 'TE', 'Opp'], [self.options[3]]))
        self.assertFalse(self.matches(['WR', 'TE', 'DST'], [self.options[3]]))

    def test_primary_choices_are_alternatives(self):
        self.assertTrue(self.matches(['WR'], self.options))
        self.assertTrue(self.matches(['WR', 'TE', 'Opp'], self.options))
        self.assertTrue(self.matches(['RB'], []))

    def test_any_includes_no_stack_and_all_stack_sizes(self):
        any_rule = [self.ns['ANY_STACK_OPTION']]
        for players in (['Unrelated'], ['WR'], ['WR', 'TE'], ['WR', 'TE', 'WR2', 'Opp']):
            self.assertTrue(self.matches(players, any_rule))
        self.assertFalse(self.matches(['Unrelated'], any_rule, self.secondary[:1]))

    def test_no_stack_and_mixed_choices(self):
        no_stack = self.ns['NO_STACK_OPTION']
        self.assertTrue(self.matches(['RB', 'Opp', 'Unrelated'], [no_stack]))
        self.assertFalse(self.matches(['WR'], [no_stack]))
        self.assertTrue(self.matches(['Unrelated'], [no_stack, self.options[1]]))
        self.assertTrue(self.matches(['WR', 'TE'], [no_stack, self.options[1]]))
        self.assertFalse(self.matches(['WR'], [no_stack, self.options[1]]))

    def test_construction_patterns_match_selection(self):
        patterns = self.ns['full_roster_stack_patterns']
        self.assertIsNone(patterns([self.ns['ANY_STACK_OPTION'], self.options[1]]))
        self.assertIsNone(patterns([]))
        self.assertEqual(patterns([self.ns['NO_STACK_OPTION']]), [(0, False)])
        self.assertEqual(patterns([self.options[3], self.ns['NO_STACK_OPTION']]), [(2, True), (0, False)])

    def test_rb_defense_is_additional_requirement(self):
        self.assertTrue(self.matches(['WR', 'RB', 'DST'], self.options, self.secondary[:1]))
        self.assertFalse(self.matches(['WR', 'RB', 'OtherD'], self.options, self.secondary[:1]))
        self.assertFalse(self.matches(['RB', 'DST'], self.options, self.secondary[:1]))

    def test_mini_stack_must_be_another_game(self):
        self.assertTrue(self.matches(['WR', 'MiniA', 'MiniB'], self.options, self.secondary[1:]))
        self.assertFalse(self.matches(['WR', 'Opp'], self.options, self.secondary[1:]))
        self.assertFalse(self.matches(['WR', 'MiniA', 'Unrelated'], self.options, self.secondary[1:]))
        self.assertTrue(self.matches(['WR', 'RB', 'DST', 'MiniA', 'MiniB'], self.options, self.secondary))


if __name__ == '__main__':
    unittest.main()
