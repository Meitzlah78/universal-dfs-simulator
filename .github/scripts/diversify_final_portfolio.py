from pathlib import Path

path = Path("dfs_app.py")
text = path.read_text(encoding="utf-8")

old = '''            lineup_columns = portfolio_lineup_columns
            slot_count = len(lineup_columns)
            # Showdown has 6 roster spots; Classic has 9. Avoid near-duplicates
            # while keeping the selected lineups near the top of the chosen metric.
            max_shared_players = max(1, slot_count - 2)
            selected_indices = []
            selected_sets = []
            selected_keys = set()

            for idx, row in ranked_df.iterrows():
                lineup_key = tuple(str(row[col]) for col in lineup_columns)
                if lineup_key in selected_keys:
                    continue
                player_set = set(lineup_key)
                if all(
                    len(player_set.intersection(existing)) <= max_shared_players
                    for existing in selected_sets
                ):
                    selected_indices.append(idx)
                    selected_sets.append(player_set)
                    selected_keys.add(lineup_key)
                    if len(selected_indices) >= int(portfolio_count):
                        break

            # Fallback ensures the requested portfolio size can still be reached.
            if len(selected_indices) < int(portfolio_count):
                for idx, row in ranked_df.iterrows():
                    lineup_key = tuple(str(row[col]) for col in lineup_columns)
                    if lineup_key in selected_keys:
                        continue
                    selected_indices.append(idx)
                    selected_keys.add(lineup_key)
                    if len(selected_indices) >= int(portfolio_count):
                        break
'''

new = '''            lineup_columns = portfolio_lineup_columns
            slot_count = len(lineup_columns)
            # Showdown has 6 roster spots; Classic has 9. Avoid near-duplicates
            # while keeping the selected lineups near the top of the chosen metric.
            max_shared_players = max(1, slot_count - 2)
            selected_indices = []
            selected_sets = []
            selected_keys = set()
            selected_player_counts = {}

            # Default portfolio diversification guard. A player may still exceed
            # 80% when the user explicitly locks that player or sets Min Exposure
            # above 80%. A lower manual Max Exposure always remains authoritative.
            auto_diversification_pct = 80.0

            def portfolio_player_limit(player_name):
                settings = control_map.get(str(player_name), {})
                try:
                    manual_max = float(settings.get("Max Exposure %", 100))
                except (TypeError, ValueError):
                    manual_max = 100.0
                try:
                    manual_min = float(settings.get("Min Exposure %", 0))
                except (TypeError, ValueError):
                    manual_min = 0.0
                manual_max = float(np.clip(manual_max, 0.0, 100.0))
                manual_min = float(np.clip(manual_min, 0.0, 100.0))
                if bool(settings.get("Lock", False)):
                    effective_max = 100.0
                elif manual_min > auto_diversification_pct:
                    effective_max = manual_max
                else:
                    effective_max = min(manual_max, auto_diversification_pct)
                if effective_max <= 0:
                    return 0
                return max(1, int(np.ceil(int(portfolio_count) * effective_max / 100.0)))

            def portfolio_lineup_fits_player_limits(player_set):
                return all(
                    selected_player_counts.get(str(player), 0) < portfolio_player_limit(player)
                    for player in player_set
                )

            def record_portfolio_players(player_set):
                for player in player_set:
                    name = str(player)
                    selected_player_counts[name] = selected_player_counts.get(name, 0) + 1

            for idx, row in ranked_df.iterrows():
                lineup_key = tuple(str(row[col]) for col in lineup_columns)
                if lineup_key in selected_keys:
                    continue
                player_set = set(lineup_key)
                if not portfolio_lineup_fits_player_limits(player_set):
                    continue
                if all(
                    len(player_set.intersection(existing)) <= max_shared_players
                    for existing in selected_sets
                ):
                    selected_indices.append(idx)
                    selected_sets.append(player_set)
                    selected_keys.add(lineup_key)
                    record_portfolio_players(player_set)
                    if len(selected_indices) >= int(portfolio_count):
                        break

            # Fallback relaxes only the overlap rule. It still respects player
            # exposure limits, preventing one strong play from silently reaching 100%.
            if len(selected_indices) < int(portfolio_count):
                for idx, row in ranked_df.iterrows():
                    lineup_key = tuple(str(row[col]) for col in lineup_columns)
                    if lineup_key in selected_keys:
                        continue
                    player_set = set(lineup_key)
                    if not portfolio_lineup_fits_player_limits(player_set):
                        continue
                    selected_indices.append(idx)
                    selected_keys.add(lineup_key)
                    record_portfolio_players(player_set)
                    if len(selected_indices) >= int(portfolio_count):
                        break
'''

if new not in text:
    if old not in text:
        raise SystemExit("Could not find final portfolio selection block")
    text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print("Added default 80% final-portfolio diversification guard while preserving manual exposure controls.")
