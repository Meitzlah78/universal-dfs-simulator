"""Anonymous joint QB-stack/bring-back frequencies for full-roster fields.

Stack counts are grouped as 0, 1, 2+ WR/TE teammates; bring-backs as 0, 1+.
Profiles are averaged per contest, never by player identity or realized scores.
"""
import numpy as np


def learned_construction_distribution(profiles):
    values=[]
    for profile in profiles:
        item=profile.get('joint_stack_bringback',{})
        counts=np.asarray(item.get('counts',[]),dtype=float)
        if counts.shape==(6,) and np.isfinite(counts).all() and (counts>=0).all() and counts.sum()>=100 and counts.sum()>=.8*profile.get('lineups',counts.sum()):
            values.append(counts/counts.sum())
    return np.mean(values,axis=0).tolist() if values else None


def construction_labels(picks, teams, positions, opponents):
    skills=picks[:,1:8]
    catcher=np.array([bool(set(p.split('/')) & {'WR','TE'}) for p in positions])
    offense=np.array([bool(set(p.split('/')) & {'RB','WR','TE'}) for p in positions])
    stack=((teams[skills]==teams[picks[:,0],None]) & catcher[skills]).sum(axis=1)
    back=((teams[skills]==opponents[picks[:,0],None]) & offense[skills]).any(axis=1)
    return np.minimum(stack,2)*2+back.astype(int)


def allocate_counts(weights,total):
    weights=np.asarray(weights,float)
    if not np.isfinite(weights).all() or (weights<0).any() or weights.sum()<=0:
        raise ValueError('Invalid construction frequencies')
    raw=weights/weights.sum()*int(total);quota=np.floor(raw).astype(int)
    order=np.argsort(-(raw-quota),kind='stable');quota[order[:int(total)-quota.sum()]]+=1
    return quota


def construction_quotas(field,target):
    """Preserve learned joint construction and conditional salary frequencies."""
    distribution=field.attrs.get('construction_distribution')
    if distribution is None or 'Construction Group' not in field:
        _,groups=np.unique(field.Salary.to_numpy(),return_inverse=True)
        return groups,allocate_counts(np.bincount(groups),target)
    labels=field['Construction Group'].to_numpy(int)
    pairs=np.column_stack([labels,field.Salary.to_numpy()])
    unique,groups=np.unique(pairs,axis=0,return_inverse=True)
    sizes=np.bincount(groups);quotas=np.zeros(len(sizes),int)
    desired=allocate_counts(distribution,target)
    for label,budget in enumerate(desired):
        eligible=np.flatnonzero(unique[:,0]==label)
        if budget and not len(eligible):raise ValueError('Learned construction has no supported proposals')
        if budget:quotas[eligible]=allocate_counts(sizes[eligible],budget)
    if (quotas>sizes).any():raise ValueError('Insufficient proposals for learned construction/salary mix')
    return groups,quotas
