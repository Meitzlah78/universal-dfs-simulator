import unittest
from datetime import datetime, timezone

from dk_showdown_history import walk_forward_batches


class DKShowdownWalkForwardProtocolTests(unittest.TestCase):
    def test_every_eligible_contest_is_held_out_exactly_once(self):
        contests = [
            {"id": "a", "lock_time": datetime(2026, 10, 10, 20, tzinfo=timezone.utc)},
            {"id": "b", "lock_time": datetime(2026, 10, 11, 20, tzinfo=timezone.utc)},
            {"id": "c", "lock_time": datetime(2026, 10, 12, 20, tzinfo=timezone.utc)},
            {"id": "d", "lock_time": datetime(2026, 10, 12, 20, tzinfo=timezone.utc)},
            {"id": "e", "lock_time": datetime(2026, 10, 13, 20, tzinfo=timezone.utc)},
        ]
        batches = walk_forward_batches(contests, min_training_contests=2)
        held_out = [c["id"] for batch in batches for c in batch["targets"]]
        self.assertCountEqual(held_out, ["c", "d", "e"])
        self.assertEqual(len(held_out), len(set(held_out)))

    def test_training_pool_only_expands_after_batch_completes(self):
        t1 = datetime(2026, 10, 10, 20, tzinfo=timezone.utc)
        t2 = datetime(2026, 10, 11, 20, tzinfo=timezone.utc)
        t3 = datetime(2026, 10, 12, 20, tzinfo=timezone.utc)
        t4 = datetime(2026, 10, 13, 20, tzinfo=timezone.utc)
        contests = [
            {"id": "old1", "lock_time": t1}, {"id": "old2", "lock_time": t2},
            {"id": "game-a", "lock_time": t3}, {"id": "game-b", "lock_time": t3},
            {"id": "later", "lock_time": t4},
        ]
        batches = walk_forward_batches(contests, min_training_contests=2)
        batch3 = next(b for b in batches if b["lock_time"] == t3)
        batch4 = next(b for b in batches if b["lock_time"] == t4)
        self.assertCountEqual([c["id"] for c in batch3["training"]], ["old1", "old2"])
        self.assertCountEqual([c["id"] for c in batch4["training"]], ["old1", "old2", "game-a", "game-b"])

    def test_input_order_cannot_change_temporal_training_sets(self):
        contests = [
            {"id": "late", "lock_time": datetime(2026, 10, 13, 20, tzinfo=timezone.utc)},
            {"id": "early", "lock_time": datetime(2026, 10, 10, 20, tzinfo=timezone.utc)},
            {"id": "middle", "lock_time": datetime(2026, 10, 11, 20, tzinfo=timezone.utc)},
        ]
        batches = walk_forward_batches(contests)
        late = next(b for b in batches if b["targets"][0]["id"] == "late")
        self.assertEqual([c["id"] for c in late["training"]], ["early", "middle"])


if __name__ == "__main__":
    unittest.main()
