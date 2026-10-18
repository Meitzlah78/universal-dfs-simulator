"""Exercise the app loader without importing Streamlit or making network calls."""
import ast
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import patch
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


class DffShowdownDiscoveryTests(TestCase):
    def load(self, fail_default=False):
        tree = ast.parse((Path(__file__).resolve().parents[1] / "dfs_app.py").read_text())
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in
                 {"download_public_projection_table", "normalize_projection_player_name"}]
        for node in nodes:
            node.decorator_list = []
        scope = {"pd": pd, "np": np}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "dfs_app.py", "exec"), scope)
        today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
        calls = []

        def response(text="", payload=None):
            return SimpleNamespace(text=text, raise_for_status=lambda: None, json=lambda: payload)

        def get(url, **kwargs):
            calls.append((url, kwargs.get("params")))
            if "/data/slates/" in url:
                if kwargs.get("params"):
                    return response(payload={"slates": [
                        {"showdown_flag": 0, "url": "CLASSIC"},
                        {"showdown_flag": 1, "url": "25D4F"}]})
                return response(payload={"dates": [{"start_date": today}], "slates": []})
            if url.endswith("/showdown-single-game-projections/") and fail_default:
                raise RuntimeError("default slate unavailable")
            if "slate=25D4F" in url:
                return response('''<table><tr class="projections-listing" data-name="Jordan Love" data-ppg_proj="21.0"></tr>
                    <tr class="projections-listing" data-name="CeeDee Lamb" data-ppg_proj="20.2"></tr>
                    <tr class="projections-listing" data-name="No Projection" data-ppg_proj="NaN"></tr></table>''')
            return response('''<script>window.url = '25D4A';</script>
                <tr class="projections-listing" data-name="Derrick Henry" data-ppg_proj="17.9"></tr>''')

        with patch.dict("sys.modules", {"requests": SimpleNamespace(get=get)}), patch.object(pd, "read_html", return_value=[]):
            result = scope["download_public_projection_table"](
                "DFF", "DraftKings Showdown", ["Jordan Love", "CeeDee Lamb"])
        return result, calls

    def test_discovers_matching_slate_from_ajax_menu_and_parses_attributes(self):
        result, calls = self.load()
        self.assertEqual(result, {"jordanlove": 21.0, "ceedeelamb": 20.2})
        self.assertTrue(any(params and params["url"] == "25D4A" for _, params in calls))
        self.assertFalse(any("slate=CLASSIC" in url for url, _ in calls))

    def test_failed_default_page_does_not_skip_discovery(self):
        result, _ = self.load(fail_default=True)
        self.assertEqual(result, {"jordanlove": 21.0, "ceedeelamb": 20.2})


if __name__ == "__main__":
    main()
