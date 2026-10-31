"""Initial score-driven garbage-time rotations; thresholds are not calibrated."""
import numpy as np


def planned_minutes(rotation, size):
    return np.stack([(rotation==player).sum(axis=(1,2)) for player in range(size)],axis=1)


def garbage_time_court(court, minutes, elapsed, margin, *, enabled=True):
    """Replace at most two >=28-minute players with scheduled active reserves.

    Both winning and losing teams use the same absolute score-margin rule.
    Only players already present in the planned rotation may gain court time.
    """
    result=np.array(court,copy=True)
    changed=np.zeros(len(result),bool)
    if not enabled:return result,changed
    time=np.asarray(elapsed);lead=np.abs(margin)
    flags=(time<2880)&(((time>=2520)&(lead>=20))|((time>=2700)&(lead>=15)))
    ids=np.flatnonzero(flags)
    if not len(ids):return result,changed
    plan=np.asarray(minutes)[ids];line=result[ids].copy()
    # Reserve means outside the five highest planned minute totals. Ties are
    # deterministic; zero-minute/inactive/padded players are never promoted.
    rank=np.argsort(np.argsort(-plan,axis=1,kind='stable'),axis=1,kind='stable')
    available=(plan>0)&(rank>=5)&(plan<28)
    order=np.argsort(np.where(available,plan,np.inf),axis=1,kind='stable')
    rows=np.arange(len(ids))
    for _ in range(2):
        on_minutes=plan[rows[:,None],line]
        star=np.argmax(on_minutes,axis=1)
        can_remove=on_minutes[rows,star]>=28
        choices=available[rows[:,None],order]&~(order[:,:,None]==line[:,None,:]).any(axis=2)
        first=np.argmax(choices,axis=1)
        ok=can_remove&choices.any(axis=1)
        line[rows[ok],star[ok]]=order[rows[ok],first[ok]]
        changed[ids[ok]]=True
    result[ids]=line
    return result,changed
