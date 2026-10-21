import unittest
import pandas as pd
from test_nba_late_swap import LateSwapTests
from simmah_nba_late_swap import swap_entries,revalidate_current_locks,export_swaps

class LateSwapLockRefreshTests(unittest.TestCase):
    def test_tipoff_during_processing_preserves_original_and_exports(self):
        fixture=LateSwapTests();fixture.setUp()
        result=swap_entries(fixture.template,'42-99',fixture.pool,now=fixture.now)
        self.assertNotEqual(result['lineups'][0],fixture.ids)
        later=fixture.now+pd.Timedelta(hours=3)
        current=revalidate_current_locks(fixture.pool,result,now=later)
        self.assertEqual(current['lineups'][0],fixture.ids)
        self.assertEqual(current['entries_preserved_by_lock_check'],1)
        self.assertEqual(current['report'].iloc[0]['Changes'],0)
        self.assertNotEqual(result['lineups'][0],fixture.ids)
        export_swaps(fixture.template,'42-99',fixture.pool,current,now=later)
        safe=revalidate_current_locks(fixture.pool,result,now=fixture.now)
        self.assertEqual(safe['entries_preserved_by_lock_check'],0)
        self.assertEqual(safe['lineups'],result['lineups'])
