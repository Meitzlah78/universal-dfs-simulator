"""Exercise a browser download and its independent audit against Streamlit."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen
from zipfile import ZipFile

PAYLOAD = b"Entry ID,CPT\r\n1,2\r\n"
ROOT = Path(__file__).resolve().parents[1]


def fixture():
    import pandas as pd
    import streamlit as st
    import simmah_export_history as history
    from simmah_slate_workspaces import workspace_download_button

    archives = Path(os.environ["SIMMAH_TEST_ARCHIVES"])
    if not hasattr(history, "fixture_original_persist"):
        history.fixture_original_persist = history.persist_checkpoint
        history.persist_checkpoint = lambda record, _: history.fixture_original_persist(record, archives)

    def save_snapshot(expected):
        assert expected == PAYLOAD
        count = st.session_state.get("fixture_callbacks", 0) + 1
        st.session_state["fixture_callbacks"] = count
        (archives / "callback-count").write_text(str(count))

    context = {
        "format": "DraftKings Showdown", "contest_id": "123", "kind": "entries",
        "player_pool": pd.DataFrame({"Name": ["Player A"], "Projection": [12.0]}),
    }
    workspace_download_button(
        st, "Download entries", PAYLOAD, "exact.csv", "text/csv", key="entries",
        on_click=save_snapshot, args=(PAYLOAD,), export_checkpoint=context,
    )
    workspace_download_button(
        st, "Download disabled", b"", "disabled.csv", "text/csv", key="disabled",
        disabled=True, export_checkpoint={**context, "contest_id": "456"},
    )


def check_browser(url, archives):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=os.environ.get("SIMMAH_CHROMIUM_PATH"),
        )
        page = browser.new_page(accept_downloads=True)
        page.goto(url)
        frames = page.frame_locator('iframe[title$="simmah_audited_download"]')
        button = frames.nth(0).get_by_role("button", name="Download entries")
        expect(button).to_be_enabled(timeout=15000)
        expect(frames.nth(1).get_by_role("button", name="Download disabled")).to_be_disabled()
        assert not list(archives.glob("*.zip"))
        for count in (1, 2):
            with page.expect_download(timeout=8000) as download:
                button.click()
            result = download.value
            assert result.suggested_filename == "exact.csv"
            assert result.path().read_bytes() == PAYLOAD
            expect(page.get_by_text("Saved exports — latest first", exact=True)).to_be_visible(timeout=8000)
            deadline = time.monotonic() + 8
            while len(list(archives.glob("*.zip"))) < count and time.monotonic() < deadline:
                time.sleep(0.05)
            assert len(list(archives.glob("*.zip"))) == count
        expect(page.get_by_test_id("stException")).to_have_count(0)
        browser.close()

    assert (archives / "callback-count").read_text() == "2"
    for archive in archives.glob("*.zip"):
        with ZipFile(archive) as export:
            assert export.read("export.csv") == PAYLOAD
            assert b"Player A,12.0" in export.read("player_pool.csv")


def run():
    with tempfile.TemporaryDirectory() as directory, socket.socket() as port_reservation:
        archives = Path(directory)
        port_reservation.bind(("127.0.0.1", 0))
        port = port_reservation.getsockname()[1]
        port_reservation.close()
        url = f"http://127.0.0.1:{port}"
        env = {**os.environ, "PYTHONPATH": str(ROOT), "SIMMAH_TEST_ARCHIVES": directory}
        with (archives / "streamlit.log").open("w") as log:
            server = subprocess.Popen(
                [sys.executable, "-m", "streamlit", "run", __file__, "--server.headless=true",
                 "--browser.gatherUsageStats=false", "--server.address=127.0.0.1",
                 f"--server.port={port}", "--", "--fixture"],
                cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 15
                while True:
                    try:
                        with urlopen(url + "/_stcore/health", timeout=1):
                            break
                    except (URLError, TimeoutError):
                        if server.poll() is not None or time.monotonic() >= deadline:
                            raise
                        time.sleep(0.1)
                check_browser(url, archives)
            except Exception:
                print((archives / "streamlit.log").read_text(), file=sys.stderr)
                raise
            finally:
                server.terminate()
                server.wait(timeout=10)


if __name__ == "__main__":
    if "--fixture" in sys.argv:
        fixture()
    else:
        run()
