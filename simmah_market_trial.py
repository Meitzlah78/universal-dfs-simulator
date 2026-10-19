"""Offline market challenger. Not imported by the live app."""
import re
import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp
from lxml import html


def key(name):
    return re.sub('[^a-z0-9]', '', str(name).lower())


def implied_probability(american):
    odds=float(str(american).replace('−','-').replace('+',''))
    if not np.isfinite(odds) or abs(odds)<100:
        raise ValueError('Invalid American price')
    return -odds/(100-odds) if odds<0 else 100/(100+odds)


def parse_covers_pairs(document):
    """Extract same-book, same half-point line O/U pairs; never pair best prices."""
    root=html.fromstring(document)
    pairs=[]; rejected=0
    for button in root.xpath('//button[contains(@class,"compareOddsBtn")]'):
        label=button.get('data-linkcont','').split('-nfl-')[-1]
        if '-' not in label:continue
        markets=('score_a_touchdown','passing_yards','rushing_yards','receiving_yards','receptions_made','rushing_attempts','passing_attempts','passing_completions','interceptions_thrown','rush_and_rec_yards','passing_and_rushing_yards')
        market=next((m for m in markets if label.startswith(m+'-')),label.rsplit('-',1)[0])
        block=button.getparent()
        names=block.xpath('.//*[contains(@class,"playerContainer")]//*[contains(@class,"category")]/text()')
        if not names:continue
        name=' '.join(' '.join(names).split())
        for row in block.xpath('.//dialog//table[contains(@class,"compareOddsTable")]/tbody/tr'):
            books=row.xpath('./th//img/@alt')
            book=books[0].removesuffix(' logo') if books else ''
            sides={}
            for cell in row.xpath('./td'):
                lines=cell.xpath('.//span[contains(@class,"oddsSideLineText")]/text()')
                prices=cell.xpath('.//span[contains(@class,"americanOdds")]/text()')
                if len(lines)!=1 or len(prices)!=1:continue
                m=re.fullmatch(r'([ou])\s*([0-9]+(?:\.[0-9]+)?)',lines[0].strip())
                if m:sides[m[1]]=(float(m[2]),prices[0].strip())
            if not book or set(sides)!={'o','u'} or sides['o'][0]!=sides['u'][0] or sides['o'][0]%1!=.5:
                rejected+=1;continue
            over=implied_probability(sides['o'][1]);under=implied_probability(sides['u'][1])
            if not 1 <= over+under <= 1.30:
                rejected+=1;continue
            pairs.append(dict(Name=name,Market=market,Book=book,Line=sides['o'][0],
                Over=sides['o'][1],Under=sides['u'][1],FairOver=over/(over+under)))
    # The main document and market fragments may repeat cards.
    unique={(x['Name'],x['Market'],x['Book'],x['Line']):x for x in pairs}
    return list(unique.values()),rejected


def tilt_outcomes(features, targets, ridge=.05, min_ess_fraction=.25):
    """Soft moment fit of shared game weights; never modify player stat lines.

    Ridge and the effective-sample-size floor are fixed before outcomes are known.
    Infeasible features are rejected by the caller. Soft fit reports residuals.
    """
    x=np.asarray(features,dtype=float);p=np.asarray(targets,dtype=float)
    if x.ndim!=2 or x.shape[1]!=len(p) or x.shape[0]<2 or not np.isfinite(x).all() or not np.isfinite(p).all() or ((p<=0)|(p>=1)).any():
        raise ValueError('Invalid market constraints')
    if ridge<=0 or not 0<min_ess_fraction<=1:raise ValueError('Invalid regularization')
    n=len(x)
    def loss(theta):
        z=x@theta;logz=logsumexp(z);w=np.exp(z-logz)
        return float(logz-np.log(n)-p@theta+.5*ridge*(theta@theta)),x.T@w-p+ridge*theta
    fit=minimize(loss,np.zeros(len(p)),jac=True,method='L-BFGS-B',options={'maxiter':150,'ftol':1e-10})
    if not fit.success:raise ValueError('Market fit failed: '+str(fit.message))
    z=x@fit.x;w=np.exp(z-logsumexp(z));uniform=np.full(n,1/n)
    # Temper the entire joint game distribution, preserving event conservation.
    strength=1.
    while 1/np.dot(w,w)<min_ess_fraction*n:
        strength*=.9;w=uniform+strength*(np.exp(z-logsumexp(z))-uniform)
    return w,dict(effective_sample_size=float(1/np.dot(w,w)),tempering=strength,
        mean_abs_probability_residual=float(np.abs(x.T@w-p).mean()),iterations=int(fit.nit))
