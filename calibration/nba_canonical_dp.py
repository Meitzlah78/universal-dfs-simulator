"""Exact NBA roster-set DP, with flexible-position assignment counted once.

The state carries the *set of reachable slot masks*, not an individual slot
assignment. Two valid assignments of the same physical roster are therefore
one support point. Determinization is exact; explicit state/time budgets fail
closed rather than switching to sampled support.
"""
from collections import Counter
from fractions import Fraction
from functools import lru_cache
from math import gcd, lcm
from time import perf_counter
import numpy as np
from scipy.special import logsumexp

POSITIONS = {'PG','SG','SF','PF','C'}


class StateBudgetExceeded(RuntimeError):
    pass


def rules(platform, slot_names=None):
    if platform == 'DraftKings':
        names=('PG','SG','SF','PF','C','G','F','UTIL')
        allowed=({'PG'},{'SG'},{'SF'},{'PF'},{'C'},{'PG','SG'},{'SF','PF'},POSITIONS)
        return dict(platform=platform,slots=names,eligibility=allowed,salary_cap=50000,max_from_team=8,min_teams=2,min_games=2)
    if platform != 'FanDuel':
        raise ValueError('NBA platform must be DraftKings or FanDuel')
    names=tuple(slot_names or ('PG','SG','SF','PF','C','G/F','F/C','UTIL','UTIL'))
    if names == ('PG','PG','SG','SG','SF','SF','PF','PF','C'):
        allowed=tuple({s} for s in names)
    elif names == ('PG','SG','SF','PF','C','G/F','F/C','UTIL','UTIL'):
        allowed=({'PG'},{'SG'},{'SF'},{'PF'},{'C'},{'PG','SG','SF','PF'},{'SF','PF','C'},POSITIONS,POSITIONS)
    else:
        raise ValueError('Unrecognized FanDuel NBA roster layout; do not guess slot rules')
    return dict(platform=platform,slots=names,eligibility=allowed,salary_cap=60000,max_from_team=4,min_teams=3,min_games=1)


def slot_mask(player, rule):
    return sum(1<<i for i,allowed in enumerate(rule['eligibility']) if set(player['positions']) & allowed)


@lru_cache(maxsize=100000)
def extend_family(family, eligible):
    result=0
    while family:
        bit=family & -family
        used=bit.bit_length()-1
        choices=eligible & ~used
        while choices:
            slot=choices & -choices
            result |= 1 << (used | slot)
            choices-=slot
        family-=bit
    return result


def legal_roster(chosen, rule):
    if len(chosen)!=len(rule['slots']) or len({p['id'] for p in chosen})!=len(chosen):
        return False
    if sum(p['salary'] for p in chosen)>rule['salary_cap']:
        return False
    teams=Counter(p['team'] for p in chosen)
    if len(teams)<rule['min_teams'] or max(teams.values())>rule['max_from_team']:
        return False
    if len({p['game'] for p in chosen})<rule['min_games']:
        return False
    # Independent bipartite matching validator, separate from DP-family logic.
    candidates=[sum(1<<j for j,p in enumerate(chosen) if set(p['positions'])&allowed)
                for allowed in rule['eligibility']]
    candidates.sort(key=int.bit_count)
    @lru_cache(None)
    def assign(slot,used):
        if slot==len(candidates):return True
        options=candidates[slot]&~used
        while options:
            bit=options&-options
            if assign(slot+1,used|bit):return True
            options-=bit
        return False
    return assign(0,0)


class CanonicalGraph:
    def __init__(self, players, rule, coordinate=None, *, forced=(), max_states=1500000, max_seconds=90):
        started=perf_counter()
        self.players=sorted(players,key=lambda p:(p['game'],p['team'],p['id']))
        self.rule=rule
        if len({p['id'] for p in players})!=len(players):raise ValueError('Duplicate physical NBA player IDs')
        for team in {p['team'] for p in players}:
            if len({p['game'] for p in players if p['team']==team})!=1:
                raise ValueError('NBA team occurs in multiple slate games; team-boundary aggregation is not valid')
        self.coordinate=dict(coordinate or {p['id']:i for i,p in enumerate(players)})
        self.dimension=max(self.coordinate.values(),default=-1)+1
        size=len(rule['slots']);full_bit=1<<((1<<size)-1);forced=set(forced)
        # Distinct games imply distinct teams on a validated one-game-per-team
        # slate. DK's redundant team counters can therefore be omitted exactly.
        track_team=rule['max_from_team']<size or rule['min_teams']>rule['min_games']
        unit=rule['salary_cap']
        for p in players:unit=gcd(unit,p['salary'])
        if unit<=0:raise ValueError('Positive integral NBA salary grid required')
        cap=rule['salary_cap']//unit
        # Exact suffix assignment-cost bounds. For each slot subset, this is
        # the cheapest way to fill it with distinct remaining players. Invalid
        # prefix assignment masks can then be removed with one integer AND.
        masks=1<<size;infinite=10**12
        suffix=[None]*(len(self.players)+1)
        suffix[-1]=[0]+[infinite]*(masks-1)
        for i in range(len(self.players)-1,-1,-1):
            old=suffix[i+1];new=old.copy();eligible=slot_mask(self.players[i],rule)
            price=self.players[i]['salary']//unit
            for used,cost in enumerate(old):
                if cost==infinite:continue
                options=eligible&~used
                while options:
                    bit=options&-options;target=used|bit
                    new[target]=min(new[target],cost+price);options-=bit
            suffix[i]=new
        # k, spent, assignment-family, current-team count, completed-team count,
        # any current-game player, completed-game count.
        states=[(0,0,1,0,0,0,0)];paths=[1];layers=[];total=1
        for step,p in enumerate(self.players):
            if perf_counter()-started>max_seconds:raise StateBudgetExceeded('NBA graph construction time budget reached')
            eligible=slot_mask(p,rule);salary=p['salary']//unit
            remaining=self.players[step+1:];left=len(remaining)
            cheapest=sorted(q['salary']//unit for q in remaining)
            lower=[0]
            for value in cheapest:lower.append(lower[-1]+value)
            completion=sorted((cost,1<<used) for used in range(masks)
                              if (cost:=suffix[step+1][(masks-1)^used])<=cap)
            permitted=[];family=0;cursor=0
            for budget in range(cap+1):
                while cursor<len(completion) and completion[cursor][0]<=budget:
                    family|=completion[cursor][1];cursor+=1
                permitted.append(family)
            next_team=step+1==len(self.players) or self.players[step+1]['team']!=p['team']
            next_game=step+1==len(self.players) or self.players[step+1]['game']!=p['game']
            following={};numbers=[];skip_src=[];skip_dst=[];add_src=[];add_dst=[]
            def insert(state,paths_count):
                k,spent,family,team_count,teams,game_any,games=state
                if k>size or size-k>left or spent>cap or spent+lower[size-k]>cap:
                    return None
                family &= permitted[cap-spent]
                if not family:return None
                if next_team:
                    teams=min(rule['min_teams'],teams+bool(team_count)) if track_team else 0;team_count=0
                if next_game:
                    games=min(rule['min_games'],games+bool(game_any));game_any=0
                if games>=rule['min_games']:game_any=0
                key=(k,spent,family,team_count,teams,game_any,games)
                if key not in following:
                    following[key]=len(following);numbers.append(0)
                index=following[key];numbers[index]+=paths_count
                return index
            for source,state in enumerate(states):
                k,spent,family,team_count,teams,game_any,games=state
                if p['id'] not in forced:
                    target=insert(state,paths[source])
                    if target is not None:skip_src.append(source);skip_dst.append(target)
                if k<size and (not track_team or team_count<rule['max_from_team']) and spent+salary<=cap:
                    new_family=extend_family(family,eligible)
                    if new_family:
                        target=insert((k+1,spent+salary,new_family,team_count+1 if track_team else 0,teams,1,games),paths[source])
                        if target is not None:add_src.append(source);add_dst.append(target)
            if not following:raise ValueError('No legal NBA support under these rules')
            total+=len(following)
            if total>max_states:raise StateBudgetExceeded(f'NBA graph state budget reached ({total:,} > {max_states:,}) at player {step+1}/{len(self.players)}; no sampled fallback')
            layers.append(dict(previous_size=len(states),next_size=len(following),
                skip_src=np.asarray(skip_src,dtype=np.int32),skip_dst=np.asarray(skip_dst,dtype=np.int32),
                add_src=np.asarray(add_src,dtype=np.int32),add_dst=np.asarray(add_dst,dtype=np.int32),
                role_coordinate=self.coordinate.get(p['id']),player_id=p['id']))
            states=list(following);paths=numbers
        terminals=[i for i,(k,spent,family,tc,teams,ga,games) in enumerate(states)
                   if k==size and family&full_bit and (not track_team or teams>=rule['min_teams']) and games>=rule['min_games']]
        if not terminals:raise ValueError('No terminal legal NBA rosters')
        self.count=sum(paths[i] for i in terminals)
        self.nodes=[dict(layers=layers,final_size=len(states),terminal_indices=np.array(terminals,dtype=int),
                         terminal_features=np.zeros((len(terminals),self.dimension)))]
        self.stats=dict(canonical_support_count=self.count,stored_states=total,
                        edges=sum(len(l['skip_src'])+len(l['add_src']) for l in layers),
                        graph_index_bytes=sum(l[k].nbytes for l in layers for k in ('skip_src','skip_dst','add_src','add_dst')),
                        construction_seconds=perf_counter()-started,salary_unit=unit,
                        coordinate_dimension=self.dimension,canonical_position_assignments=True)

    def remap(self, coordinate):
        self.coordinate=dict(coordinate);self.dimension=len(coordinate)
        self.stats['coordinate_dimension']=self.dimension
        for node in self.nodes:
            for layer in node['layers']:layer['role_coordinate']=coordinate.get(layer['player_id'])
            node['terminal_features']=np.zeros((len(node['terminal_indices']),self.dimension))

    def evaluate(self, theta, gradient=True):
        theta=np.asarray(theta,float)
        if theta.shape!=(self.dimension,) or not np.isfinite(theta).all():raise ValueError('Invalid NBA potential vector')
        node=self.nodes[0];forward=[np.array([0.])]
        for layer in node['layers']:
            out=np.full(layer['next_size'],-np.inf);previous=forward[-1]
            np.logaddexp.at(out,layer['skip_dst'],previous[layer['skip_src']])
            j=layer['role_coordinate'];potential=theta[j] if j is not None else 0.
            np.logaddexp.at(out,layer['add_dst'],previous[layer['add_src']]+potential)
            forward.append(out)
        terminal=node['terminal_indices'];z=float(logsumexp(forward[-1][terminal]))
        if not np.isfinite(z):raise FloatingPointError('Nonfinite NBA partition')
        self.last_normalization_error=float(abs(np.exp(forward[-1][terminal]-z).sum()-1))
        if not gradient:return z
        means=np.zeros(self.dimension);tail=np.full(node['final_size'],-np.inf);tail[terminal]=0
        for i in range(len(node['layers'])-1,-1,-1):
            layer=node['layers'][i];j=layer['role_coordinate'];potential=theta[j] if j is not None else 0.
            if j is not None:
                means[j]+=np.exp(forward[i][layer['add_src']]+potential+tail[layer['add_dst']]-z).sum()
            previous=np.full(layer['previous_size'],-np.inf)
            np.logaddexp.at(previous,layer['skip_src'],tail[layer['skip_dst']])
            np.logaddexp.at(previous,layer['add_src'],potential+tail[layer['add_dst']]);tail=previous
        if not np.isfinite(means).all():raise FloatingPointError('Nonfinite NBA expectations')
        return z,means

    def extreme(self, coefficients, maximize=True):
        """Exact integer linear optimization, also returns a roster witness."""
        sign=1 if maximize else -1
        if sum(abs(int(v)) for v in coefficients.values())>=2**60:
            raise ValueError('Exact reconstruction coefficients exceed the integer audit budget')
        node=self.nodes[0];negative=-(2**62)
        tail=np.full(node['final_size'],negative,dtype=np.int64);tail[node['terminal_indices']]=0;tails=[tail]
        for layer in reversed(node['layers']):
            previous=np.full(layer['previous_size'],negative,dtype=np.int64)
            previous[layer['skip_src']]=tail[layer['skip_dst']]
            valid=tail[layer['add_dst']]!=negative
            src=layer['add_src'][valid];dst=layer['add_dst'][valid]
            values=tail[dst]+sign*int(coefficients.get(layer['player_id'],0))
            np.maximum.at(previous,src,values)
            tail=previous;tails.append(tail)
        tails=tails[::-1];source=0;roster=[]
        for i,layer in enumerate(node['layers']):
            take=np.flatnonzero(layer['add_src']==source)
            chosen=False
            if len(take):
                dest=int(layer['add_dst'][take[0]])
                value=tails[i+1][dest]
                if value!=negative and value+sign*int(coefficients.get(layer['player_id'],0))==tails[i][source]:
                    roster.append(layer['player_id']);source=dest;chosen=True
            if not chosen:
                skip=np.flatnonzero(layer['skip_src']==source)
                if not len(skip):raise AssertionError('Missing exact extreme-path witness')
                source=int(layer['skip_dst'][skip[0]])
        return sign*int(tails[0][0]),tuple(sorted(roster))


def exact_basis(graph, observed, players, max_extra_witnesses=32):
    """Modular independent witnesses + rational reconstruction + global proof.

    A witness dependency is never assumed global. Each proposed relation is
    checked by exact integer min/max optimization over the complete DP graph.
    A violating roster is added as a new witness and rank is recomputed.
    """
    ids=[p['id'] for p in players];index={pid:i+1 for i,pid in enumerate(ids)}
    prime=2147483647;rows=[];basis={}
    def add(roster):
        vector=np.zeros(len(ids)+1,dtype=np.int64);vector[0]=1
        for pid in roster:vector[index[pid]]=1
        reduced=vector.copy()
        for col,pivot in sorted(basis.items()):
            if reduced[col]:reduced=(reduced-int(reduced[col])*pivot)%prime
        nonzero=np.flatnonzero(reduced)
        if not len(nonzero):return False
        col=int(nonzero[0]);reduced=reduced*pow(int(reduced[col]),prime-2,prime)%prime
        basis[col]=reduced;rows.append(vector)
        return True
    for roster in observed:
        add(roster)
        if len(rows)==len(ids)+1:break
    for attempt in range(max_extra_witnesses+1):
        matrix=[[Fraction(int(x)) for x in row] for row in rows];pivots=[];r=0
        for col in range(len(ids)+1):
            pivot=next((i for i in range(r,len(matrix)) if matrix[i][col]),None)
            if pivot is None:continue
            matrix[r],matrix[pivot]=matrix[pivot],matrix[r]
            div=matrix[r][col];matrix[r]=[v/div for v in matrix[r]]
            for i in range(len(matrix)):
                if i!=r and matrix[i][col]:
                    mult=matrix[i][col];matrix[i]=[a-mult*b for a,b in zip(matrix[i],matrix[r])]
            pivots.append(col);r+=1
            if r==len(matrix):break
        assert pivots and pivots[0]==0
        failed=False
        for col in set(range(len(ids)+1))-set(pivots):
            coefficients=[matrix[j][col] for j in range(len(pivots))]
            denominator=lcm(*(c.denominator for c in coefficients))
            weights={ids[col-1]:denominator}
            constant=0
            for pivot,c in zip(pivots,coefficients):
                if pivot==0:constant=-int(c*denominator)
                else:weights[ids[pivot-1]]=weights.get(ids[pivot-1],0)-int(c*denominator)
            active_weights=[weights.get(p['id'],0) for p in graph.players]
            if len(set(active_weights))==1:
                # Exact fixed-roster-size identity, including inactive zero
                # columns. No graph scan is needed to re-prove this constant.
                low=high=active_weights[0]*len(graph.rule['slots'])
                witness=upper=next(iter(observed))
            else:
                low,witness=graph.extreme(weights,False)
                high,upper=graph.extreme(weights,True)
            if low+constant or high+constant:
                if not add(witness if low+constant else upper):raise AssertionError('Failed rank-witness expansion')
                failed=True;break
        if failed:continue
        # The existing binary128 reconstruction format uses integer matrices.
        # Never truncate a non-integral exact relation into that format.
        if any(c.denominator!=1 for row in matrix for c in row):
            raise ValueError('Exact NBA feature reconstruction needs a rational-matrix kernel; no rounded rank reduction applied')
        T=np.zeros((len(ids)+1,len(pivots)-1),dtype=np.int64);offset=np.zeros(len(ids)+1,dtype=np.int64)
        for col in range(len(ids)+1):
            offset[col]=int(matrix[0][col])
            for j in range(1,len(pivots)):T[col,j-1]=int(matrix[j][col])
        return {ids[c-1]:j for j,c in enumerate(pivots[1:])},T,offset,dict(
            exact_feature_rank=len(pivots),optimizer_dimension=len(pivots)-1,
            modular_prime=prime,witness_rosters=len(rows),
            exact_global_dependency_checks=True,witness_expansions=attempt)
    raise ValueError('NBA exact rank witness budget reached; rank remains unresolved')
