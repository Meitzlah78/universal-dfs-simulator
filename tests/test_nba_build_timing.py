import unittest
from simmah_nba_build_timing import BuildTiming

class BuildTimingTests(unittest.TestCase):
    def test_phase_breakdown_sums_to_total_and_snapshots_are_independent(self):
        now=[10.]
        timer=BuildTiming(clock=lambda:now[0])
        now[0]=12.;timer.advance('Simulating candidate scenarios')
        now[0]=19.;first=timer.snapshot('running')
        self.assertEqual(first['total_seconds'],9)
        self.assertEqual(first['phase_seconds']['Simulating candidate scenarios'],7)
        now[0]=22.;timer.advance('Selecting portfolio')
        now[0]=25.;last=timer.snapshot('stopped',platform='DraftKings')
        self.assertEqual(last['stage'],'Selecting portfolio')
        self.assertEqual(sum(last['phase_seconds'].values()),last['total_seconds'])
        self.assertEqual(first['phase_seconds']['Simulating candidate scenarios'],7)
        self.assertEqual(last['phase_seconds']['Simulating candidate scenarios'],10)
        self.assertEqual(last['platform'],'DraftKings')

    def test_repeated_progress_in_same_stage_does_not_reset_clock(self):
        now=[0.];timer=BuildTiming(clock=lambda:now[0])
        timer.advance('Scoring')
        now[0]=5.;timer.advance('Scoring')
        now[0]=12.;summary=timer.snapshot('complete')
        self.assertEqual(summary['phase_seconds']['Scoring'],12)
        self.assertEqual(summary['total_seconds'],12)

if __name__=='__main__':unittest.main()
