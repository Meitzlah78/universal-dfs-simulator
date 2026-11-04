"""Small per-build phase timer; no Streamlit, engine or background work."""
from time import perf_counter


class BuildTiming:
    def __init__(self,clock=perf_counter):
        self.clock=clock
        self.started=self.phase_started=clock()
        self.stage='Preparing build'
        self.phases={}

    def advance(self,stage):
        if stage==self.stage:return
        now=self.clock()
        self.phases[self.stage]=self.phases.get(self.stage,0.)+now-self.phase_started
        self.stage=stage;self.phase_started=now

    def snapshot(self,status,**metadata):
        now=self.clock();phases=dict(self.phases)
        phases[self.stage]=phases.get(self.stage,0.)+now-self.phase_started
        return dict(metadata,status=status,total_seconds=now-self.started,
                    stage=self.stage,phase_seconds=phases)
