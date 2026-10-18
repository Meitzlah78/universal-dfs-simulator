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
    def load(self, fail_default=False, repeat=False, broken_hint=False):
        tree = ast.parse((Path(__file__).resolve().parents[1] / "dfs_app.py").read_text())
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in
                 {"download_public_projection_table", "normalize_projection_player_name"}]
        for node in nodes:
            node.decorator_list = []
        state = {"selected_dk_contest": {"name": "Dime Package (DAL @ GB)"}}
        scope = {"pd": pd, "np": np, "st": SimpleNamespace(session_state=state)}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "dfs_app.py", "exec"), scope)
        today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
        calls = []
        love_projection = [21.0]

        def response(text="", payload=None):
            return SimpleNamespace(text=text, raise_for_status=lambda: None, json=lambda: payload)

        def get(url, **kwargs):
            calls.append((url, kwargs.get("params")))
            if url == "https://www.dailyfantasyfuel.com/broken":
                raise RuntimeError("stale slate URL")
            if "/data/slates/" in url:
                if kwargs.get("params"):
                    return response(payload={"slates": [
                        {"showdown_flag": 0, "url": "CLASSIC"},
                        {"showdown_flag": 1, "url": "25D4F", "slate_type": "DAL @ GB"}]})
                return response(payload={"dates": [{"start_date": today}], "slates": []})
            if url.endswith("/showdown-single-game-projections/") and fail_default:
                raise RuntimeError("default slate unavailable")
            if "slate=25D4F" in url:
                return response(f'''<table><tr class="projections-listing" data-name="Jordan Love" data-team="GB" data-opp="DAL" data-ppg_proj="{love_projection[0]}"></tr>
                    <tr class="projections-listing" data-name="CeeDee Lamb" data-team="DAL" data-opp="GB" data-ppg_proj="20.2"></tr>
                    <tr class="projections-listing" data-name="No Projection" data-ppg_proj="NaN"></tr></table>''')
            return response('''<script>window.url = '25D4A';</script>
                <tr class="projections-listing" data-name="Jordan Love" data-team="GB" data-opp="MIN" data-ppg_proj="99"></tr>
                <tr class="projections-listing" data-name="Christian Watson" data-team="GB" data-opp="MIN" data-ppg_proj="50"></tr>''')

        with patch.dict("sys.modules", {"requests": SimpleNamespace(get=get)}), patch.object(pd, "read_html", return_value=[]):
            if broken_hint:
                state["verified_dff_slate_routes"] = {
                    ("draftkings", ("ceedeelamb", "christianwatson", "jordanlove"), ("DAL", "GB")): "https://www.dailyfantasyfuel.com/broken"}
            result = scope["download_public_projection_table"](
                "DFF", "DraftKings Showdown", ["Jordan Love", "CeeDee Lamb", "Christian Watson"], ("DAL", "GB"))
            if repeat:
                calls.clear()
                love_projection[0] = 22.0
                result = scope["download_public_projection_table"](
                    "DFF", "DraftKings Showdown", ["Jordan Love", "CeeDee Lamb", "Christian Watson"], ("DAL", "GB"))
        return result, calls

    def test_discovers_matching_slate_from_ajax_menu_and_parses_attributes(self):
        result, calls = self.load()
        self.assertEqual(result, {"jordanlove": 21.0, "ceedeelamb": 20.2})
        self.assertTrue(any(params and params["url"] == "25D4A" for _, params in calls))
        self.assertFalse(any("slate=CLASSIC" in url for url, _ in calls))

    def test_rejects_wrong_game_with_two_matching_green_bay_players(self):
        result, _ = self.load()
        self.assertEqual(result["jordanlove"], 21.0)
        self.assertNotIn("christianwatson", result)

    def test_failed_default_page_does_not_skip_discovery(self):
        result, _ = self.load(fail_default=True)
        self.assertEqual(result, {"jordanlove": 21.0, "ceedeelamb": 20.2})

    def test_refresh_reuses_route_but_downloads_new_projection_values(self):
        result, calls = self.load(repeat=True)
        self.assertEqual(result["jordanlove"], 22.0)
        self.assertEqual(len(calls), 1)
        self.assertIn("slate=25D4F", calls[0][0])

    def test_broken_route_falls_back_to_discovery(self):
        result, calls = self.load(broken_hint=True)
        self.assertEqual(result["jordanlove"], 21.0)
        self.assertTrue(any(params for _, params in calls))


if __name__ == "__main__":
    main()
