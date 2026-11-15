"""Passive audit counters; no model fitting, policy changes or future-season reads."""
import numpy as np

ZONES=['inside5','opp35_to5','opp50_to35','own25_to50','own_goal_to25']
SCRIPTS=['late_trailing','end_half','neutral','other']
FOURTH_COLS=['proposals','opportunities','go','punts','fg','conversions','candidate_expected_go','baseline_expected_go']
PLAY_COLS=['n','yards','g20','g40','field20','field40','conversions','td','success','nonpositive','below3']


def zone(field):
    return np.select([field<5,field<35,field<=50,field<=75],[0,1,2,3],default=4).astype(int)


def script(remaining,margin,qtr):
    end=(qtr==2)&(remaining<=1920)&(remaining>=1800)
    neutral=(np.abs(margin)<=8)&(remaining>300)&~end
    return np.select([(remaining<=300)&(margin<0),end,neutral],[0,1,2],default=3).astype(int)


def fourth_index(d):
    return (zone(d['field'])*2+(d['togo']>2).astype(int))*4+script(d['remaining'],d['margin'],d['qtr'])


class Observer:
    def __init__(self):
        self.fourth=np.zeros((40,len(FOURTH_COLS)))
        self.play=np.zeros((2,12,len(PLAY_COLS)))
        self.dropbacks=0
    def __call__(self,kind,d):
        if kind=='fourth':
            idx=fourth_index(d);executed=d['executed'];go=d['go']&executed
            values=[np.ones(len(idx)),executed,go,d['punt'],d['fg'],np.zeros(len(idx)),d.get('candidate_expected_go',np.zeros(len(idx))),d.get('baseline_expected_go',np.zeros(len(idx)))]
            for c,v in enumerate(values):self.fourth[:,c]+=np.bincount(idx,weights=v,minlength=40)
        elif kind=='play':
            self.dropbacks+=int(d['passing'].sum())
            gain=d['gain'];threshold=np.where(d['down']==1,.4*d['togo'],np.where(d['down']==2,.6*d['togo'],d['togo']))
            idx=(d['down']-1)*3+np.select([d['togo']<=2,d['togo']<=6],[0,1],default=2)
            values=[np.ones(len(gain)),gain,gain>=20,gain>=40,d['field']>=20,d['field']>=40,d['conversion'],d['td'],(gain>=threshold)&~d['turnover'],gain<=0,gain<3]
            for k,mask in enumerate([d['running'],d['caught']]):
                for c,v in enumerate(values):self.play[k,:,c]+=np.bincount(idx[mask],weights=v[mask],minlength=12)
            loc=d['down']==4
            if loc.any():self.fourth[:,5]+=np.bincount(fourth_index({k:v[loc] for k,v in d.items() if k in ['field','togo','remaining','margin','qtr']}),weights=d['conversion'][loc],minlength=40)
        else:raise ValueError('Unknown passive event type')
    def result(self):return {'fourth':self.fourth.tolist(),'play':self.play.tolist(),'dropbacks':self.dropbacks}
