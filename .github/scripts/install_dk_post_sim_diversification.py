"""Install post-Contest-Sim DK Showdown diversification controls into dfs_app.py.

BUILD and Contest Sim results remain cached. This transform only changes final
portfolio selection: Portfolio mode uses EV ordering without a hidden overlap
rule; Min Uniques applies the user's explicit 0..6 requirement after simulation.
"""
from pathlib import Path

APP = Path("dfs_app.py")
text = APP.read_text(encoding="utf-8")

import_anchor = "from dk_showdown_engine import (\n"
new_import = "from dk_portfolio_selection import select_post_sim_portfolio\n"
if new_import not in text:
    if import_anchor not in text:
        raise SystemExit("DK engine import anchor not found")
    text = text.replace(import_anchor, new_import + import_anchor, 1)

ui_anchor = '''    portfolio_metric = PORTFOLIO_METRICS[
        portfolio_metric_label
    ]
'''
ui_replacement = ui_anchor + '''
    diversification_mode = st.radio(
        "Diversification after Contest Sim",
        ["Portfolio", "Min Uniques"],
        horizontal=True,
        key="post_sim_diversification_mode",
        help=(
            "Portfolio keeps the strongest contest-EV lineups without a forced overlap rule. "
            "Min Uniques applies an exact player-difference requirement after Contest Sim."
        ),
    )
    min_uniques = 0
    if diversification_mode == "Min Uniques":
        min_uniques = st.number_input(
            "Minimum unique players",
            min_value=0,
            max_value=max(0, len(portfolio_lineup_columns)),
            value=0,
            step=1,
            key="post_sim_min_uniques",
            help="0 means no forced diversification; 1 means two selected lineups may share at most 5 of 6 players, etc.",
        )

    # These are explicit user controls from the player table. They are applied
    # only while selecting the final portfolio from already-simulated lineups.
    post_sim_max_exposure = {}
    post_sim_captain_max_exposure = {}
    if "edited_controls" in locals() and isinstance(edited_controls, pd.DataFrame) and not edited_controls.empty:
        if "Name" in edited_controls.columns and "Max Exposure %" in edited_controls.columns:
            post_sim_max_exposure = {
                str(row["Name"]): float(row["Max Exposure %"])
                for _, row in edited_controls.iterrows()
                if pd.notna(row.get("Name")) and pd.notna(row.get("Max Exposure %"))
            }
        if "Name" in edited_controls.columns and "Captain Max %" in edited_controls.columns:
            post_sim_captain_max_exposure = {
                str(row["Name"]): float(row["Captain Max %"])
                for _, row in edited_controls.iterrows()
                if pd.notna(row.get("Name")) and pd.notna(row.get("Captain Max %"))
            }
'''
if ui_anchor not in text:
    raise SystemExit("portfolio metric UI anchor not found")
text = text.replace(ui_anchor, ui_replacement, 1)

signature_anchor = '''        or st.session_state.get("portfolio_metric_used") != selection_metric
    ):
'''
signature_replacement = '''        or st.session_state.get("portfolio_metric_used") != selection_metric
        or st.session_state.get("portfolio_diversification_mode_used") != diversification_mode
        or st.session_state.get("portfolio_min_uniques_used") != int(min_uniques)
    ):
'''
if signature_anchor not in text:
    raise SystemExit("portfolio selection signature anchor not found")
text = text.replace(signature_anchor, signature_replacement, 1)

# Replace both legacy branches (locked and unlocked) with one selector call.
# The selector itself preserves locks, counts them toward exposure, and requires
# newly selected lineups to satisfy Min Uniques relative to locks.
start_marker = '''        old_portfolio = st.session_state.get("portfolio_df")

        if (
'''
end_marker = '''        st.session_state["portfolio_df"] = portfolio_df
'''
start = text.find(start_marker)
if start < 0:
    raise SystemExit("legacy portfolio selection block start not found")
end = text.find(end_marker, start)
if end < 0:
    raise SystemExit("portfolio state write marker not found")

replacement = '''        old_portfolio = st.session_state.get("portfolio_df")
        locked_df = None
        if (
            isinstance(old_portfolio, pd.DataFrame)
            and "Locked" in old_portfolio.columns
            and all(col in old_portfolio.columns for col in portfolio_lineup_columns)
        ):
            locked_df = old_portfolio[old_portfolio["Locked"] == True].copy()

        # Diversification happens only after Contest Sim. Portfolio mode does
        # not impose a hidden overlap rule or automatic 90% exposure ceiling.
        # Min Uniques applies exactly the user's requested player difference.
        requested_uniques = int(min_uniques) if diversification_mode == "Min Uniques" else 0
        portfolio_df = select_post_sim_portfolio(
            results_df,
            int(portfolio_count),
            metric=selection_metric,
            min_uniques=requested_uniques,
            lineup_columns=tuple(portfolio_lineup_columns),
            max_exposure=post_sim_max_exposure,
            captain_max_exposure=post_sim_captain_max_exposure,
            locked_df=locked_df,
        )
        if len(portfolio_df) < int(portfolio_count):
            if diversification_mode == "Min Uniques":
                st.warning(
                    f"Only {len(portfolio_df):,} lineups satisfy Min Uniques = {requested_uniques} "
                    "and the current manual exposure limits. Constraints were not silently relaxed."
                )
            else:
                st.warning(
                    f"Only {len(portfolio_df):,} lineups satisfy the current manual exposure limits. "
                    "Constraints were not silently relaxed."
                )

'''
text = text[:start] + replacement + text[end:]

state_anchor = '''        st.session_state["portfolio_control_signature"] = current_control_signature
'''
state_replacement = state_anchor + '''        st.session_state["portfolio_diversification_mode_used"] = diversification_mode
        st.session_state["portfolio_min_uniques_used"] = int(min_uniques)
'''
if state_anchor not in text:
    raise SystemExit("portfolio control state anchor not found")
text = text.replace(state_anchor, state_replacement, 1)

# Fail closed if the hidden legacy diversification rules survived.
for forbidden in (
    "auto_diversification_pct = 90.0",
    "max_shared_players = max(1, slot_count - 2)",
    "available_count = max(",
):
    if forbidden in text:
        raise SystemExit(f"legacy diversification rule survived transform: {forbidden}")

if "locked_df=locked_df" not in text:
    raise SystemExit("locked portfolio was not routed through post-sim selector")

APP.write_text(text, encoding="utf-8")
