"""Offline bounded redistribution kernel; no fitted script probabilities or live use.

Caller must supply pregame/simulated states, never observed final game labels.
This kernel deliberately does not choose transfer amplitudes from audit outcomes.
"""
import numpy as np


def redistribute(minutes,means,*,state='neutral',transfer_budget=0.,foul_cuts=None):
    """Transfer team minutes with exact conservation and [0,48] bounds.

    Blowout: top7 -> remaining active reserves. Tight: ranks8+ -> top7.
    Foul cuts: selected player -> other active players, proportional to headroom.
    Missing recipient support is explicitly reported, not silently invented.
    This is a trial-total prototype, not a time-resolved six-foul engine.
    """
    v=np.array(minutes,dtype=float,copy=True);means=np.asarray(means,float)
    if v.ndim!=1 or v.shape!=means.shape or not np.isfinite(v).all() or not np.isfinite(means).all():raise ValueError('Invalid rotation')
    if np.any((v<0)|(v>48)) or not np.isclose(v.sum(),240):raise ValueError('Require legal 240-minute team rotation')
    if np.any(means<0) or np.any(v[means==0]>0):raise ValueError('Inactive player minutes')
    if state not in ['neutral','blowout','tight']:raise ValueError('Unknown state')
    if not np.isfinite(transfer_budget) or transfer_budget<0:raise ValueError('Invalid budget')
    rank=np.flatnonzero(means>0)[np.argsort(-means[means>0],kind='stable')];core=rank[:7];bench=rank[7:];ledger=[]
    def move(donors,receivers,wanted,label):
        donors=np.asarray(donors,int);receivers=np.asarray(receivers,int)
        take=v[donors].sum();room=(48-v[receivers]).sum();amount=min(wanted,take,room)
        if amount>0:
            v[donors]-=amount*v[donors]/take;v[receivers]+=amount*(48-v[receivers])/room
        ledger.append(dict(reason=label,requested=float(wanted),transferred=float(amount),unallocated=float(wanted-amount)))
    for index,cut in (foul_cuts or {}).items():
        if not isinstance(index,(int,np.integer)) or index not in rank or not np.isfinite(cut) or cut<0:raise ValueError('Invalid foul cut')
        move([index],[j for j in rank if j!=index and j not in (foul_cuts or {})],min(cut,v[index]),'foul')
    if state=='blowout':move(core,[j for j in bench if j not in (foul_cuts or {})],transfer_budget,state)
    if state=='tight':move(bench,[j for j in core if j not in (foul_cuts or {})],transfer_budget,state)
    if not np.isclose(v.sum(),240) or np.any(v< -1e-9) or np.any(v>48+1e-9):raise AssertionError('Conservation failed')
    # Floating-point boundary repair only; never alter a substantive transfer.
    v=np.clip(v,0.,48.)
    residual=240.-v.sum()
    if abs(residual)>1e-8:raise AssertionError('Non-numerical budget residual')
    if residual:
        choices=np.flatnonzero((means>0)&((48-v>abs(residual)) if residual>0 else (v>abs(residual))))
        if not len(choices):raise AssertionError('No numerical repair support')
        v[choices[0]]+=residual
    return v,ledger
