from pathlib import Path


def test_projected_dupes_installer_targets_actual_portfolio_export():
    text = Path('.github/scripts/install_dk_projected_dupes_output.py').read_text()
    assert 'portfolio_export_df = portfolio_df[' in text
    assert '"Projected Dupes"' in text
    assert '_dupe_values = []' in text
