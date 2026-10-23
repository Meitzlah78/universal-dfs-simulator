"""Parameterized six-player, two-team log-DP graph used by the offline runner."""
import numpy as np
from scipy.special import logsumexp

class LogDPEvaluator:
    """Compile structural state transitions, then evaluate log Z and moments.

    State (k,s,t,r): FLEX count, integer FLEX salary, team-A FLEX count,
    same-team WR/TE FLEX count for designated QB MVPs (zero otherwise).
    Forward log-DP gives log Z. Backward log-DP gives inclusion marginals.
    Terminal feature contributions include the fixed MVP role exactly once.
    All MVP subtrees are normalized by one GLOBAL partition function.
    """
    def __init__(self, manifest, player_ids, salary_cap, *, fixed_mvp_id=None):
        self.manifest = manifest
        players = {p['platform_player_id']: p for p in manifest['players']}
        if len(set(player_ids)) != len(player_ids):
            raise ValueError('Duplicate subset ID')
        if fixed_mvp_id is not None and fixed_mvp_id not in player_ids:
            raise ValueError('Fixed MVP must be in the supplied player pool')
        self.players = [players[pid] for pid in sorted(player_ids)]
        zero = manifest['verification']['retained_zero_role_indices']
        self.keep = np.setdiff1d(np.arange(len(manifest['retained_rows'])), [0, *zero])
        self.dimension = len(self.keep)
        self.team_a = manifest['team_a']
        row_to_coordinate = {int(row): i for i, row in enumerate(self.keep)}
        roles, stacks, teams = {}, {}, {}
        for row in manifest['retained_rows']:
            if row['row_index'] not in row_to_coordinate:
                continue
            coordinate = row_to_coordinate[row['row_index']]
            if row['kind'] == 'role':
                roles[(row['role'], row['player_id'])] = coordinate
            elif row['kind'] == 'joint_qb_stack':
                stacks.setdefault(row['qb_id'], {})[row['same_team_wrte_flex_count']] = coordinate
            elif row['kind'] == 'team_count':
                teams[row['roster_player_count']] = coordinate
        self.nodes = []
        for mvp in self.players:
            if fixed_mvp_id is not None and mvp['platform_player_id'] != fixed_mvp_id:
                continue
            if mvp['historical_mvp_count'] == 0:
                continue
            pid = mvp['platform_player_id']
            pool = [p for p in self.players if p['platform_player_id'] != pid
                    and p['historical_flex_count'] > 0]
            budget = salary_cap - mvp['salary_mvp']
            states = [(0, 0, 0, 0)]
            layers = []
            for step, p in enumerate(pool):
                following = {}
                skip_src, skip_dst, add_src, add_dst = [], [], [], []
                left = len(pool) - step - 1

                def insert(state):
                    if state not in following:
                        following[state] = len(following)
                    return following[state]

                for source, state in enumerate(states):
                    k, spent, ne, receivers = state
                    if k + left >= 5:
                        skip_src.append(source)
                        skip_dst.append(insert(state))
                    if k < 5 and spent + p['salary_flex'] <= budget and k + 1 + left >= 5:
                        new = (k + 1, spent + p['salary_flex'], ne + (p['team'] == self.team_a),
                               receivers + (pid in stacks and p['team'] == mvp['team']
                                            and p['position'] in {'WR', 'TE'}))
                        add_src.append(source)
                        add_dst.append(insert(new))
                arrays = [np.array(v, dtype=np.int64)
                          for v in (skip_src, skip_dst, add_src, add_dst)]
                layers.append(dict(previous_size=len(states), next_size=len(following),
                                   skip_src=arrays[0], skip_dst=arrays[1],
                                   add_src=arrays[2], add_dst=arrays[3],
                                   role_coordinate=roles.get(('FLEX', p['platform_player_id']))))
                states = list(following)
            terminal_indices, terminal_features = [], []
            for i, (k, spent, ne, receivers) in enumerate(states):
                total_ne = ne + (mvp['team'] == self.team_a)
                if k != 5 or not 1 <= total_ne <= 5 or spent > budget:
                    continue
                feature = np.zeros(self.dimension)
                for coordinate in (roles.get(('MVP', pid)), teams.get(total_ne),
                                   stacks.get(pid, {}).get(receivers)):
                    if coordinate is not None:
                        feature[coordinate] = 1.
                terminal_indices.append(i)
                terminal_features.append(feature)
            if terminal_indices:
                self.nodes.append(dict(mvp_id=pid, layers=layers, final_size=len(states),
                                       terminal_indices=np.array(terminal_indices, dtype=int),
                                       terminal_features=np.vstack(terminal_features)))
        if not self.nodes:
            raise ValueError('No feasible miniature support')
        self.stats = dict(mvp_subtrees=len(self.nodes),
                          stored_layer_states=sum(l['previous_size'] for n in self.nodes for l in n['layers']),
                          terminal_states=sum(len(n['terminal_indices']) for n in self.nodes),
                          directed_edges=sum(len(l['skip_src']) + len(l['add_src'])
                                             for n in self.nodes for l in n['layers']))

    def evaluate(self, theta, gradient=True):
        theta = np.asarray(theta, dtype=float)
        if theta.shape != (self.dimension,) or not np.all(np.isfinite(theta)):
            raise ValueError('theta must be a finite vector of shape (self.dimension,)')
        evaluations, terminal_logs = [], []
        for node in self.nodes:
            forward = [np.array([0.])]
            for layer in node['layers']:
                out = np.full(layer['next_size'], -np.inf)
                previous = forward[-1]
                np.logaddexp.at(out, layer['skip_dst'], previous[layer['skip_src']])
                coordinate = layer['role_coordinate']
                potential = theta[coordinate] if coordinate is not None else 0.
                np.logaddexp.at(out, layer['add_dst'], previous[layer['add_src']] + potential)
                forward.append(out)
            potentials = node['terminal_features'] @ theta
            log_weights = forward[-1][node['terminal_indices']] + potentials
            if not np.all(np.isfinite(log_weights)):
                raise FloatingPointError('Nonfinite reachable terminal potential')
            evaluations.append((node, forward, potentials, log_weights))
            terminal_logs.append(log_weights)
        log_z = float(logsumexp(np.concatenate(terminal_logs)))
        if not np.isfinite(log_z):
            raise FloatingPointError('Nonfinite global log partition')
        if not gradient:
            return log_z
        expectation = np.zeros(self.dimension)
        for node, forward, potentials, log_weights in evaluations:
            expectation += node['terminal_features'].T @ np.exp(log_weights - log_z)
            tail = np.full(node['final_size'], -np.inf)
            tail[node['terminal_indices']] = potentials
            for i in range(len(node['layers']) - 1, -1, -1):
                layer = node['layers'][i]
                coordinate = layer['role_coordinate']
                potential = theta[coordinate] if coordinate is not None else 0.
                inclusion = forward[i][layer['add_src']] + potential + tail[layer['add_dst']] - log_z
                if coordinate is not None:
                    expectation[coordinate] += np.exp(inclusion).sum()
                previous_tail = np.full(layer['previous_size'], -np.inf)
                np.logaddexp.at(previous_tail, layer['skip_src'], tail[layer['skip_dst']])
                np.logaddexp.at(previous_tail, layer['add_src'], potential + tail[layer['add_dst']])
                tail = previous_tail
        if not np.all(np.isfinite(expectation)):
            raise FloatingPointError('Nonfinite feature expectations')
        return log_z, expectation
