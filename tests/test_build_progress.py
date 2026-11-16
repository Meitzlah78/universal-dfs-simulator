import unittest
from simmah_build_progress import ui_progress


class Widget:
    def __init__(self):self.updates=[]
    def progress(self,fraction,**kwargs):self.updates.append((fraction,kwargs['text']))


class ProgressTests(unittest.TestCase):
    def test_dense_updates_are_bounded_and_final_is_delivered(self):
        widget=Widget();now=[0.];report=ui_progress(widget,clock=lambda:now[0])
        for i in range(626):
            now[0]=i*.005;report(i/625,str(i))
        self.assertLessEqual(len(widget.updates),15)
        self.assertEqual(widget.updates[0],(0.,'0'))
        self.assertEqual(widget.updates[-1],(1.,'625'))
    def test_new_stage_reset_and_slow_updates_stay_visible(self):
        widget=Widget();now=[0.];report=ui_progress(widget,clock=lambda:now[0])
        report(.5,'first');report(.1,'next stage');report(0,'reset');report(1,'done')
        now[0]=1;report(.4,'later')
        self.assertEqual(len(widget.updates),5)

if __name__=='__main__':unittest.main()
