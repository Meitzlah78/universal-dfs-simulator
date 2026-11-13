"""Offline basketball state primitives. Not imported by the live engine.

Mechanics are explicit; probabilities and coaching thresholds are research
assumptions until temporal validation. This is not a promoted full-game model.
"""
from dataclasses import dataclass,field
import numpy as np
from simmah_nba_minutes import allocate_minutes


def sample_minutes(means,sd,trials,seed):
    """Conserve 240 minutes across named active players; no latent bench IDs."""
    means=np.asarray(means,float);sd=np.asarray(sd,float)
    if (means.ndim!=1 or sd.shape!=means.shape or len(means)<5 or
        not np.isfinite(means).all() or not np.isfinite(sd).all() or
        (means<0).any() or (means>48).any() or (sd<0).any() or
        abs(means.sum()-240)>1e-6 or trials<1):raise ValueError('Complete legal minutes and uncertainty required')
    rng=np.random.default_rng(seed)
    weights=np.maximum(means+rng.normal(size=(trials,len(means)))*sd,1e-8)
    weights[:,means==0]=0
    return allocate_minutes(weights)


@dataclass
class RotationState:
    """Event-time minutes/foul coupling for one named active team.

    Call choose() after each foul and at every coaching transition. A player
    at six fouls is ineligible from that instant onward. Insufficient legal
    support is explicit, never a silent return of a disqualified player.
    """
    targets:np.ndarray
    foul_trouble:bool=True
    blowout:bool=False
    fouls:np.ndarray=field(init=False)
    seconds:np.ndarray=field(init=False)

    def __post_init__(self):
        self.targets=np.asarray(self.targets,float).copy()
        if (self.targets.ndim!=1 or not np.isfinite(self.targets).all() or
            (self.targets<0).any() or (self.targets>48).any() or
            abs(self.targets.sum()-240)>1e-6):raise ValueError('Complete 240-minute target ledger required')
        self.fouls=np.zeros(len(self.targets),int);self.seconds=np.zeros(len(self.targets))

    def personal_foul(self,player):
        if not isinstance(player,(int,np.integer)) or not 0<=player<len(self.fouls):raise ValueError('Invalid foul player')
        if self.fouls[player]>=6:raise ValueError('Disqualified player cannot commit another on-court foul')
        self.fouls[player]+=1
        return bool(self.fouls[player]==6)

    def choose(self,remaining,margin=0):
        if not np.isfinite(remaining) or not 0<remaining<=2880 or not np.isfinite(margin):raise ValueError('Valid regulation game state required')
        eligible=(self.targets>0)&(self.fouls<6)
        if eligible.sum()<5:raise ValueError('Fewer than five eligible players; unsupported roster state')
        # Remaining target deficit supplies opportunity priority. No after-game
        # actuals enter the choice; noisy targets are sampled before the game.
        priority=60*self.targets-self.seconds
        quarter=min(4,1+int((2880-remaining)//720))
        if self.foul_trouble and quarter<4:
            priority=priority-2880*(self.fouls>=quarter+1)
        if self.blowout and remaining<=360 and abs(margin)>=20:
            priority=priority-2880*(self.targets>=28)
        priority=np.where(eligible,priority,-np.inf)
        return np.argsort(-priority,kind='stable')[:5]

    def advance(self,court,seconds):
        court=np.asarray(court)
        if (court.shape!=(5,) or court.dtype.kind not in 'iu' or len(set(court))!=5 or
            (court<0).any() or (court>=len(self.targets)).any() or
            (self.fouls[court]>=6).any() or (self.targets[court]<=0).any() or
            not np.isfinite(seconds) or seconds<0):raise ValueError('Legal court and elapsed interval required')
        if self.seconds.sum()+5*seconds>14400+1e-6:raise ValueError('Regulation minute budget exceeded')
        self.seconds[court]+=seconds


@dataclass
class PossessionClock:
    game:float=2880.
    period:float=720.
    shot:float=24.

    def elapse(self,seconds):
        if not np.isfinite(seconds) or seconds<0:raise ValueError('Nonnegative elapsed clock time required')
        consumed=min(seconds,self.game,self.period,self.shot)
        self.game-=consumed;self.period-=consumed;self.shot-=consumed
        # A period expiring with the shot clock is a period end, not a turnover.
        status='period_end' if self.period<=1e-9 else ('shot_clock_violation' if self.shot<=1e-9 else 'live')
        return consumed,status

    def change_possession(self):self.shot=24.
    def offensive_rebound(self):self.shot=14.

    def next_period(self):
        if self.period>1e-9 or self.game<=0:raise ValueError('No next regulation period available')
        self.period=min(720.,self.game);self.shot=24.


def sample_shot(split,rng):
    """split = player's 3PA/FGA, 2P%, 3P%; no team-rate substitution."""
    split=np.asarray(split,float)
    if split.shape!=(3,) or not np.isfinite(split).all() or (split<0).any() or (split>1).any():raise ValueError('Validated player shooting split required')
    three=bool(rng.random()<split[0]);made=bool(rng.random()<split[2 if three else 1])
    return {'attempts':1,'three_attempt':int(three),'made':int(made),'points':int(made)*(3 if three else 2)}


def free_throws(kind,make_probability,rng):
    """Caller must first credit the basket for and-one; tech retains possession.

    Returns only final-attempt rebound eligibility. A technical miss is dead;
    technical events do not terminate or reset the possession clock here.
    """
    trips={'and_one':1,'technical':1,'two_shot':2,'three_shot':3}
    if kind not in trips or not np.isfinite(make_probability) or not 0<=make_probability<=1:raise ValueError('Explicit legal FT trip and player FT probability required')
    made=rng.random(trips[kind])<make_probability
    return {'attempts':len(made),'made':int(made.sum()),'points':int(made.sum()),
            'live_rebound':bool(kind!='technical' and not made[-1]),
            'retains_possession':kind=='technical'}


def simulate_minutes_fouls(means,sd,fouls_per_minute,trials,seed,*,foul_trouble=True):
    """Regulation-only integration harness, six-second coaching grid.

    Foul intensities must be supplied from pregame training. Poisson foul timing
    and deficit-based lineup selection are challengers, not fitted NBA behavior.
    Full scoring/possession coupling and overtime are deliberately not claimed.
    """
    rate=np.asarray(fouls_per_minute,float)
    if rate.shape!=np.shape(means) or not np.isfinite(rate).all() or (rate<0).any():raise ValueError('Finite nonnegative per-player foul intensities required')
    rng=np.random.default_rng(seed);targets=sample_minutes(means,sd,trials,seed)
    minutes=[];counts=[];disqualified=[]
    for target in targets:
        state=RotationState(target,foul_trouble=foul_trouble);first=np.full(len(target),np.nan)
        for elapsed in range(0,2880,6):
            court=state.choose(2880-elapsed);state.advance(court,6.)
            # At most one foul per player per grid interval. Hazard conversion
            # preserves rare-event rate without allowing a post-DQ seventh foul.
            committing=court[rng.random(5)<-np.expm1(-rate[court]*.1)]
            for player in committing:
                if state.personal_foul(int(player)):first[player]=elapsed+6
        minutes.append(state.seconds/60);counts.append(state.fouls);disqualified.append(first)
    return {'minutes':np.asarray(minutes),'fouls':np.asarray(counts),
            'disqualified_at_seconds':np.asarray(disqualified),
            'live_enabled':False,'status':'offline minutes/foul integration harness; full-game validation pending'}
