"""Limit UI traffic, never numerical work or completion notifications."""
import time


def ui_progress(widget,interval=.25,clock=time.monotonic):
    last_time=float('-inf');last_fraction=None
    def report(fraction,text):
        nonlocal last_time,last_fraction
        now=clock()
        if (last_fraction is None or fraction in (0,1) or fraction<last_fraction
                or now-last_time>=interval):
            widget.progress(fraction,text=text)
            last_time=now
        last_fraction=fraction
    return report
