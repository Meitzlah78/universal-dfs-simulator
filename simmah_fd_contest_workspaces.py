"""Independent FanDuel contest builds within one uploaded slate."""
import hashlib
from copy import deepcopy

STORE = 'fanduel_contest_workspaces_v1'
ACTIVE = 'fanduel_active_contest_workspace_v1'


def belongs_to_contest(key):
    key = str(key)
    return key.startswith((
        'fd_lineups_', 'fd_simulation_', 'fd_player_sim_',
        'fd_contest_comparison_', 'fd_contest_field_', 'fd_active_signature_',
        'fd_assigned_display_', 'fd_last_completed_workflow_',
        'fd_full_roster_', 'fd_single_game_', 'fd_build_salary_range_',
        'fd_rank_', 'fd_player_pool_editor_', 'fd_player_controls_',
        'fd_manual_injury_status_',
        'nfl_excluded_games_FanDuel_',
        'portfolio_exposure_diversity_FanDuel_',
        'lineup_build_aggressiveness_FanDuel_',
        'confirmed_qb_role_signature_fanduel_',
        'field_learning_FanDuel_', 'single_stacks_FanDuel_',
        'single_game_correlation_strength_FanDuel_',
        'payscale_FanDuel ', 'saved_contest_choice_FanDuel ',
    )) or key == 'fd_saved_builds'


def activate_contest(state, template, mode, contest_id):
    """Save outgoing results and restore incoming results before its widgets render.

    Uploads and the contest selector stay shared. The complete template hash and
    roster format prevent another slate from inheriting a previous build.
    """
    scope = (str(mode), hashlib.sha256(bytes(template)).hexdigest(), str(contest_id))
    previous = state.get(ACTIVE)
    if previous is None:
        legacy_id = str((state.get('selected_fd_contest') or {}).get('id') or '')
        if legacy_id and legacy_id != str(contest_id):
            signature = state.get('fd_active_signature_' + str(mode).replace(' ', '_').lower())
            digest = signature[2] if isinstance(signature, tuple) and len(signature) == 3 and isinstance(signature[2], str) else scope[1]
            previous = (str(mode), digest, legacy_id)
    if previous == scope:
        return False
    saved = dict(state.get(STORE, {}))
    from simmah_slate_workspaces import transient_key
    forbidden = set(state.get('_slate_action_keys', ())) | set(state.get('_slate_uploader_keys', ())) | set(state.get('_slate_readonly_keys', ()))
    def retained(key):
        return belongs_to_contest(key) and key not in forbidden and not transient_key(key)
    if previous is not None:
        saved[previous] = deepcopy({key: state[key] for key in list(state)
                                    if retained(key)})
        for key in list(state):
            if belongs_to_contest(key):
                state.pop(key, None)
    # First use adopts an existing active build without discarding its results.
    if scope in saved:
        state.update(deepcopy(saved[scope]))
    # Rebuild visible ownership from the incoming contest's own restored field.
    if previous is not None:
        ownership = dict(state.get('latest_field_ownership_by_format', {}))
        ownership.pop('FanDuel ' + str(mode), None)
        state['latest_field_ownership_by_format'] = ownership
    state[STORE] = saved
    state[ACTIVE] = scope
    return previous is not None


PLAYER_CONTROLS = ('Fade', 'Lock', 'Min Exposure %', 'Max Exposure %')


def restore_player_controls(frame, state, mode):
    """Restore editable preferences without replaying an editor widget payload."""
    import pandas as pd
    saved = state.get('fd_player_controls_' + str(mode))
    if not isinstance(saved, pd.DataFrame) or 'Name' not in saved:
        return frame
    result = frame.copy()
    saved = saved.drop_duplicates('Name').set_index('Name')
    for column in PLAYER_CONTROLS:
        if column in saved and column in result:
            values = result['Name'].map(saved[column])
            result[column] = values.where(values.notna(), result[column])
    return result
