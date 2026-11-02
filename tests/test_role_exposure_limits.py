import unittest
import pandas as pd
from simmah_portfolio_selection import select_portfolio
from simmah_exposure_limits import validate_exposure_limits


class RoleCapTests(unittest.TestCase):
    def test_all_three_caps_and_role_names(self):
        for role in ("Captain", "MVP"):
            slots = [role, "FLEX1"]
            candidates = pd.DataFrame([{role: c, "FLEX1": f, "Top1": 100-i*10-j}
                for i,c in enumerate("ABCD") for j,f in enumerate("ABCD") if c != f])
            controls = {"A": {role+" Max %": 25, "Flex Max %": 25, "Max Exposure %": 50}}
            selected = select_portfolio(candidates, slots, 4, "Top1", controls, diversity=0)
            table = validate_exposure_limits(selected, slots, controls).set_index("Player")
            self.assertLessEqual(table.loc["A", role+" entries"], 1)
            self.assertLessEqual(table.loc["A", "FLEX entries"], 1)
            self.assertLessEqual(table.loc["A", "Overall entries"], 2)

    def test_manual_swap_audit_and_duplicate_entries(self):
        frame = pd.DataFrame({"Captain":["A","B","C","D"], "FLEX1":["B","A","A","A"]})
        with self.assertRaisesRegex(ValueError, "A: FLEX 3/4"):
            validate_exposure_limits(frame, ["Captain","FLEX1"], {"A":{"Flex Max %":50}})
        repeated = pd.concat([frame.iloc[:1]]*4, ignore_index=True)
        with self.assertRaisesRegex(ValueError, "A: Captain 4/4"):
            validate_exposure_limits(repeated, ["Captain","FLEX1"], {"A":{"Captain Max %":25}})

    def test_small_positive_limit_rounds_down(self):
        frame = pd.DataFrame({"Captain":["A"], "FLEX1":["B"], "Top1":[1]})
        for key in ("Max Exposure %", "Captain Max %"):
            with self.assertRaises(ValueError):
                select_portfolio(frame, ["Captain","FLEX1"], 1, "Top1", {"A":{key:30}}, diversity=0)
        with self.assertRaises(ValueError):
            select_portfolio(frame, ["Captain","FLEX1"], 1, "Top1", {"B":{"Flex Max %":30}}, diversity=0)

    def test_impossible_flex_caps_do_not_relax(self):
        frame = pd.DataFrame({"MVP":["A","B"], "FLEX1":["B","A"], "Top1":[2,1]})
        with self.assertRaises(ValueError):
            select_portfolio(frame, ["MVP","FLEX1"], 2, "Top1",
                             {"A":{"Flex Max %":0},"B":{"Flex Max %":0}}, diversity=100)


class ExportAuditTests(unittest.TestCase):
    def test_fanduel_audits_only_exact_exported_entries(self):
        from simmah_exports import build_fanduel_entry_export
        template = "entry_id,contest_id,MVP,ANYFLEX,ANYFLEX,ANYFLEX,ANYFLEX,ANYFLEX\n1,123-99,,,,,,\n"
        slots = ["MVP"] + ["FLEX"+str(i) for i in range(1,6)]
        portfolio = pd.DataFrame([list("ABCDEF"), list("GABCDE")], columns=slots)
        ids = {name:"123-"+str(i+1) for i,name in enumerate("ABCDEFG")}
        with self.assertRaisesRegex(ValueError, "A: MVP 1/1"):
            build_fanduel_entry_export(template, portfolio, ids, {"id":"123-99"},
                                      "Single Game", controls={"A":{"MVP Max %":50}})
        data, count = build_fanduel_entry_export(template, portfolio, ids, {"id":"123-99"},
                                                "Single Game", controls={"G":{"MVP Max %":0}})
        self.assertEqual(count, 1)

    def test_draftkings_export_blocks_edited_flex_violation(self):
        import ast
        import re
        from pathlib import Path
        from types import SimpleNamespace
        source = ast.parse(Path("dfs_app.py").read_text())
        function = next(node for node in source.body
                        if isinstance(node, ast.FunctionDef) and node.name == "build_dk_contest_entry_export")
        messages = []
        st = SimpleNamespace(error=messages.append, session_state={"dk_player_ids":{
            name:{"CPT":str(i+1), "FLEX":str(i+11)} for i,name in enumerate("ABCDEF")}})
        namespace = {"pd":pd, "re":re, "st":st, "is_full_game_contest_name":lambda name:True}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "dfs_app.py", "exec"), namespace)
        entries = pd.DataFrame([["1","99","Game","","","","","",""]],
                  columns=["Entry ID","Contest ID","Contest Name","CPT","FLEX","FLEX.1","FLEX.2","FLEX.3","FLEX.4"])
        lineups = pd.DataFrame([["1","12","13","14","15","16"]],
                              columns=["CPT","FLEX","FLEX","FLEX","FLEX","FLEX"])
        result = namespace["build_dk_contest_entry_export"](entries,"99",lineups,
                ["CPT"]+["FLEX"]*5,"Showdown",controls={"B":{"Flex Max %":0}})
        self.assertIsNone(result)
        self.assertIn("B: FLEX 1/1", messages[-1])

if __name__ == "__main__":
    unittest.main()
