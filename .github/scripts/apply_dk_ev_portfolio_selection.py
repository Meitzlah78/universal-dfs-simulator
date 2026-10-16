from pathlib import Path

path = Path('dfs_app.py')
text = path.read_text()

old = '''    portfolio_metric = PORTFOLIO_METRICS[
        portfolio_metric_label
    ]

    current_control_signature = tuple(
'''
new = '''    portfolio_metric = PORTFOLIO_METRICS[
        portfolio_metric_label
    ]

    # For DraftKings Showdown with a verified payout table, portfolio membership
    # is decided by selection-half contest EV.  The dropdown remains a display/
    # inspection sort only; changing it must not rebuild the set of lineups.
    _selection_payout_contest = st.session_state.get("selected_dk_contest", {})
    _selection_contest_id = str(_selection_payout_contest.get("id", ""))
    _selection_has_verified_payout = (
        is_dk_showdown
        and _selection_contest_id
        and str(st.session_state.get("contest_payout_contest_id", "")) == _selection_contest_id
        and "Expected ROI (%)" in results_df.columns
        and pd.to_numeric(results_df["Expected ROI (%)"], errors="coerce").notna().any()
    )
    selection_metric = "Expected ROI (%)" if _selection_has_verified_payout else portfolio_metric

    current_control_signature = tuple(
'''
if old not in text:
    raise SystemExit('portfolio metric anchor not found')
text = text.replace(old, new, 1)

text = text.replace(
    'or st.session_state.get("portfolio_metric_used") != portfolio_metric\n',
    'or st.session_state.get("portfolio_metric_used") != selection_metric\n',
    1,
)

# Only the two membership-ranking sorts inside the rebuild block should use EV.
needle = '''                .sort_values(
                    portfolio_metric,
                    ascending=False
                )'''
replacement = '''                .sort_values(
                    selection_metric,
                    ascending=False,
                    kind="stable"
                )'''
if needle not in text:
    raise SystemExit('locked ranking anchor not found')
text = text.replace(needle, replacement, 1)

needle = '.sort_values(portfolio_metric, ascending=False, kind="stable")'
if needle not in text:
    raise SystemExit('fresh ranking anchor not found')
text = text.replace(needle, '.sort_values(selection_metric, ascending=False, kind="stable")', 1)

# Let a genuinely strong core appear more often; exposure controls remain authoritative.
text = text.replace('            auto_diversification_pct = 80.0\n', '            auto_diversification_pct = 90.0\n', 1)
text = text.replace(
    '# above 80%. A lower manual Max Exposure always remains authoritative.\n',
    '# above 90%. A lower manual Max Exposure always remains authoritative.\n',
    1,
)
text = text.replace(
    '# 80% when the user explicitly locks that player or sets Min Exposure\n',
    '# 90% when the user explicitly locks that player or sets Min Exposure\n',
    1,
)

# Persist the metric that determined membership, not the user's inspection sort.
text = text.replace(
    '        st.session_state["portfolio_metric_used"] = portfolio_metric\n',
    '        st.session_state["portfolio_metric_used"] = selection_metric\n',
    1,
)
# The later assignment follows display sorting; keep membership provenance intact.
text = text.replace(
    '    st.session_state["portfolio_metric_used"] = portfolio_metric\n    portfolio_df = add_lineup_field_ownership(portfolio_df)\n',
    '    st.session_state["portfolio_metric_used"] = selection_metric\n    portfolio_df = add_lineup_field_ownership(portfolio_df)\n',
    1,
)

path.write_text(text)
