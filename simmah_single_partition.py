"""Experimental exact uniform-prior single-game partition via salary-grid DP.
No live imports. Two teams, MVP/CPT plus five FLEX, cap, no salary floor.
"""
import numpy as np
from scipy.optimize import minimize

class SalaryPartition:
    def __init__(self,salary,special_salary,teams,cap):
        raw=np.asarray(salary,float);special_raw=np.asarray(special_salary,float)
        if not np.isfinite(raw).all() or not np.isfinite(special_raw).all() or not np.equal(raw,np.floor(raw)).all() or not np.equal(special_raw,np.floor(special_raw)).all():raise ValueError('Exact integer-dollar salaries required')
        if not np.isfinite(cap) or cap<=0 or cap!=int(cap):raise ValueError('Positive integer-dollar cap required')
        self.salary=raw.astype(int);self.special=special_raw.astype(int);self.teams=np.asarray(teams)
        if len(self.salary)<6 or self.special.shape!=self.salary.shape or self.teams.shape!=self.salary.shape:raise ValueError('Aligned arrays required')
        if (self.salary<=0).any() or (self.special<=0).any() or len(np.unique(self.teams))!=2:raise ValueError('Positive salaries and two teams required')
        self.unit=int(np.gcd.reduce(np.r_[self.salary,self.special,int(cap)]));self.price=self.salary//self.unit
        self.special=self.special//self.unit;self.cap=int(cap)//self.unit;self.n=len(self.salary)

    def captain(self,c,tf,allowed,gradient,forced=None):
        offset=self.special[c]+(self.price[forced] if forced is not None else 0)
        budget=self.cap-offset;g=np.zeros(self.n);density=np.zeros(self.cap+1)
        if forced is not None and (forced==c or not allowed[forced]):return 0.,g,density
        required=5-(forced is not None)
        if budget<0:return 0.,g,density
        players=[i for i in range(self.n) if i!=c and i!=forced and allowed[i] and self.price[i]<=budget]
        dp=np.zeros((2,required+1,budget+1));flag=int(forced is not None and self.teams[forced]!=self.teams[c]);dp[flag,0,0]=1.;history=[]
        for i in players:
            if gradient:history.append(dp)
            z=np.exp(tf[i]);price=self.price[i];new=dp.copy()
            if self.teams[i]==self.teams[c]:new[:,1:,price:]+=z*dp[:,:-1,:-price]
            else:new[1,1:,price:]+=z*(dp[0,:-1,:-price]+dp[1,:-1,:-price])
            dp=new
        factor=np.exp(tf[forced]) if forced is not None else 1.
        density[offset:]=dp[1,required]*factor;partition=float(density.sum())
        if not gradient:return partition,g,density
        adj=np.zeros_like(dp);adj[1,required,:]=factor
        for i,before in zip(players[::-1],history[::-1]):
            z=np.exp(tf[i]);price=self.price[i];previous=adj.copy()
            if self.teams[i]==self.teams[c]:
                g[i]=np.sum(adj[:,1:,price:]*z*before[:,:-1,:-price]);previous[:,:-1,:-price]+=z*adj[:,1:,price:]
            else:
                tail=z*adj[1,1:,price:];g[i]=np.sum(tail*(before[0,:-1,:-price]+before[1,:-1,:-price]))
                previous[0,:-1,:-price]+=tail;previous[1,:-1,:-price]+=tail
            adj=previous
        if forced is not None:g[forced]=partition
        return partition,g,density

    def evaluate(self,theta,special_allowed=None,flex_allowed=None,gradient=True,forced=None):
        theta=np.asarray(theta,float)
        if theta.shape!=(2*self.n,) or not np.isfinite(theta).all():raise ValueError('Invalid role parameters')
        ca=np.ones(self.n,bool) if special_allowed is None else np.asarray(special_allowed,bool)
        fa=np.ones(self.n,bool) if flex_allowed is None else np.asarray(flex_allowed,bool)
        if ca.shape!=(self.n,) or fa.shape!=(self.n,) or not ca.any() or fa.sum()<5:raise ValueError('Invalid role support masks')
        cshift=np.max(theta[:self.n][ca]);fshift=np.max(theta[self.n:][fa]);tf=theta[self.n:]-fshift
        cw=np.exp(theta[:self.n]-cshift);cm=np.zeros(self.n);fm=np.zeros(self.n);density=np.zeros(self.cap+1)
        for c in np.flatnonzero(ca):
            z,g,d=self.captain(c,tf,fa,gradient,forced);cm[c]=cw[c]*z;fm+=cw[c]*g;density+=cw[c]*d
        total=cm.sum()
        if total<=0 or not np.isfinite(total):raise ValueError('Invalid partition')
        return float(np.log(total)+cshift+5*fshift),np.r_[cm,fm]/total,density/total

    def calibrate(self,special_target,flex_target,tolerance=1e-6,max_iterations=500):
        if not np.isfinite(tolerance) or tolerance<=0 or type(max_iterations) is not int or max_iterations<1:raise ValueError('Positive tolerance and iteration count required')
        if np.asarray(special_target).shape!=(self.n,) or np.asarray(flex_target).shape!=(self.n,):raise ValueError('Aligned special/FLEX vectors required')
        target=np.r_[special_target,flex_target].astype(float)
        if target.shape!=(2*self.n,) or not np.isfinite(target).all() or (target<0).any() or (target>1).any():raise ValueError('Finite role targets required')
        if not np.isclose(sum(special_target),1,atol=1e-10,rtol=0) or not np.isclose(sum(flex_target),5,atol=1e-10,rtol=0):raise ValueError('Invalid role totals')
        if (np.asarray(special_target)+np.asarray(flex_target)>1+1e-10).any():raise ValueError('Role exclusion violated')
        ca=np.asarray(special_target)>0;fa=np.asarray(flex_target)>0
        logcount,_,_=self.evaluate(np.zeros(2*self.n),gradient=False)
        scale=1/np.sqrt(np.maximum(target*(1-target),1e-6))
        def objective(z):
            theta=z*scale;logz,marginal,_=self.evaluate(theta,ca,fa)
            return logz-logcount-np.dot(theta,target),(marginal-target)*scale
        fit=minimize(objective,np.zeros(2*self.n),jac=True,method='L-BFGS-B',options={'maxiter':max_iterations,'gtol':1e-9,'ftol':1e-15,'maxls':50})
        theta=fit.x*scale;logz,marginal,density=self.evaluate(theta,ca,fa);error=float(np.max(np.abs(marginal-target)))
        if error>tolerance:raise ValueError(f'Nonconvergence: {error}, {fit.message}')
        return {'theta':theta,'marginal':marginal,'salary_density':density,'salary_axis':np.arange(self.cap+1)*self.unit,
            'diagnostics':{'max_ownership_error':error,'iterations':int(fit.nit),'optimizer_success':bool(fit.success),
             'optimizer_message':str(fit.message),'kl_from_full_uniform_prior':float(np.dot(theta,marginal)-logz+logcount),
             'full_support_count':int(round(np.exp(logcount))),'method':'exact salary-grid dual, uniform full prior, exact zero-target face'}}

    def role_moments(self,theta,special_target,flex_target):
        """Exact joint probabilities by conditioning on each positive FLEX event."""
        ca=np.asarray(special_target)>0;fa=np.asarray(flex_target)>0
        _,m,_=self.evaluate(theta,ca,fa)
        joint=np.zeros((2*self.n,2*self.n))
        for i in np.flatnonzero(fa):
            if m[self.n+i]>0:
                _,conditional,_=self.evaluate(theta,ca,fa,forced=int(i))
                joint[self.n+i,:]=m[self.n+i]*conditional
        joint[:self.n,self.n:]=joint[self.n:,:self.n].T
        joint[:self.n,:self.n]=np.diag(m[:self.n])
        joint=(joint+joint.T)/2
        return m,joint,joint-np.outer(m,m)
