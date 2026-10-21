"""Offline rotation trigger evaluation; no live engine wiring or fitted thresholds."""
from dataclasses import dataclass
import math

@dataclass(frozen=True)
class Trigger:
    name: str
    priority: int
    outgoing: str
    incoming: str
    min_fouls: int | None = None
    before_period: int | None = None
    min_margin: float | None = None
    max_seconds_left: float | None = None
    cooldown_seconds: float = 90.

def evaluate_triggers(floor, active, rules, *, period, seconds_left, margin,
                      fouls, elapsed, last_fired=None, dead_ball=False,
                      base_floor=None, base_due=False):
    """Choose the first legal trigger, otherwise advance an explicit base plan.

    Margin is from this team's perspective. Decisions happen only at legal
    substitution opportunities; a possession boundary alone is insufficient.
    Thresholds and replacement pairs are caller inputs, not learned facts.
    Returns a new floor and state; never mutates supplied history.
    """
    current=tuple(map(str,floor));eligible=set(map(str,active))
    if len(current)!=5 or len(set(current))!=5:raise ValueError('Five distinct on-court players required')
    if not set(current)<=eligible:raise ValueError('Current floor includes an inactive player')
    if not isinstance(period,int) or period<1 or not all(math.isfinite(float(v)) for v in [seconds_left,margin,elapsed]) or seconds_left<0 or elapsed<0:
        raise ValueError('Valid game context required')
    history=dict(last_fired or {})
    names=[r.name for r in rules]
    if len(names)!=len(set(names)):raise ValueError('Unique trigger names required')
    for r in rules:
        if not r.name or r.outgoing==r.incoming or not math.isfinite(r.cooldown_seconds) or r.cooldown_seconds<0:raise ValueError('Invalid trigger')
        if r.min_fouls is not None and (not isinstance(r.min_fouls,int) or not 0<=r.min_fouls<=6):raise ValueError('Invalid foul threshold')
        if r.before_period is not None and (not isinstance(r.before_period,int) or r.before_period<1):raise ValueError('Invalid period threshold')
        for v in [r.min_margin,r.max_seconds_left]:
            if v is not None and not math.isfinite(v):raise ValueError('Invalid trigger threshold')
        if r.max_seconds_left is not None and r.max_seconds_left<0:raise ValueError('Invalid clock threshold')
    if not dead_ball:return {'floor':current,'reason':'awaiting substitution opportunity','last_fired':history}
    for r in sorted(rules,key=lambda x:x.priority):
        out=str(r.outgoing);inc=str(r.incoming)
        if out not in current or inc in current or inc not in eligible:continue
        if elapsed-history.get(r.name,-math.inf)<r.cooldown_seconds:continue
        if r.min_fouls is not None:
            value=fouls.get(out)
            if value is None:continue  # Unknown foul count is not zero.
            if not isinstance(value,int) or not 0<=value<=6:raise ValueError('Invalid player foul count')
            if value<r.min_fouls:continue
        if r.before_period is not None and period>=r.before_period:continue
        if r.min_margin is not None and margin<r.min_margin:continue
        if r.max_seconds_left is not None and seconds_left>r.max_seconds_left:continue
        new=tuple(inc if p==out else p for p in current)
        history[r.name]=float(elapsed)
        return {'floor':new,'reason':'trigger: '+r.name,'last_fired':history}
    if base_due and base_floor is not None:
        planned=tuple(map(str,base_floor))
        if len(planned)!=5 or len(set(planned))!=5 or not set(planned)<=eligible:
            raise ValueError('Base rotation must contain five distinct active players')
        return {'floor':planned,'reason':'base rotation','last_fired':history}
    return {'floor':current,'reason':'hold','last_fired':history}
