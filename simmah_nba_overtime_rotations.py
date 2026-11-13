"""On-demand overtime schedules with the same full-batch seeded rotations.

Unused overtime periods need no allocation. Prefix pilots still draw schedules
from the full original batch, preserving the eager generator's random stream.
"""
import numpy as np
from simmah_nba_rotation_schedule import build_rotation


class OvertimeRotations:
    def __init__(self, minutes, n, seeds, periods):
        values=np.asarray(minutes,float)
        if (values.ndim!=2 or values.shape[0]!=2 or values.shape[1]<5
                or not np.isfinite(values).all() or (values<0).any()
                or (values>5).any() or not np.allclose(values.sum(axis=1),25,rtol=0,atol=1e-6)):
            raise ValueError('Complete two-team overtime minutes required')
        if not isinstance(n,int) or n<1 or not isinstance(periods,int) or not 1<=periods<=10:
            raise ValueError('Positive batch size and bounded overtime periods required')
        if len(seeds)!=2 or any(not isinstance(s,(int,np.integer)) or s<0 for s in seeds):
            raise ValueError('Two nonnegative integer overtime team seeds required')
        self.minutes=values.copy();self.minutes.setflags(write=False)
        self.full_n=n;self.n=n;self.seeds=tuple(seeds);self.periods=periods
        self.size=values.shape[1];self._cache={}

    @property
    def shape(self):return (self.n,2,self.periods,5,5)

    def _period(self, period):
        period=int(period)
        if not 0<=period<self.periods:raise IndexError('Overtime period outside supplied limit')
        if period not in self._cache:
            value=np.stack([build_rotation(np.tile(self.minutes[team],(self.full_n,1)),
                self.seeds[team]+period*11,team*self.size,period_minutes=5)
                for team in (0,1)],axis=1)
            value.setflags(write=False);self._cache[period]=value
        return self._cache[period]

    def __getitem__(self, key):
        if isinstance(key,slice):
            start,stop,step=key.indices(self.n)
            if start!=0 or step!=1:raise IndexError('Overtime views must be batch prefixes')
            view=object.__new__(type(self));view.__dict__=self.__dict__.copy();view.n=stop
            return view
        ids,team,periods,minutes=key
        ids=np.asarray(ids);periods=np.asarray(periods);minutes=np.asarray(minutes)
        if ids.ndim!=1 or periods.shape!=ids.shape or minutes.shape!=ids.shape or any(a.dtype.kind not in 'iu' for a in (ids,periods,minutes)):
            raise IndexError('Aligned overtime event indices required')
        if team not in (0,1) or (ids<0).any() or (ids>=self.n).any() or (minutes<0).any() or (minutes>=5).any():
            raise IndexError('Invalid overtime court indices')
        result=np.empty((len(ids),5),np.int32)
        for period in np.unique(periods):
            rows=periods==period
            result[rows]=self._period(period)[ids[rows],team,minutes[rows]]
        return result

    def materialize(self):
        """Reference/diagnostic tensor; production requests periods as needed."""
        return np.stack([self._period(p)[:self.n] for p in range(self.periods)],axis=2)
