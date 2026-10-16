import unittest
from datetime import datetime, timezone

from dk_showdown_history import eligible_training_contests, walk_forward_batches, walk_forward_splits


class DKShowdownTemporalLearningTests(unittest.TestCase):
    def test_future_contest_is_excluded_from_training(self):
        target = datetime(2026, 10, 12, 20, 15, tzinfo=timezone.utc)
        contests = [{"id": "earlier", "lock_time": datetime(2026, 10, 11, 20, 15, tzinfo=timezone.utc)}, {"id": "later", "lock_time": datetime(2026, 10, 15, 20, 15, tzinfo=timezone.utc)}]
        self.assertEqual([c["id"] for c in eligible_training_contests(contests, target)], ["earlier"])

    def test_same_lock_time_is_not_training_data(self):
        target = datetime(2026, 10, 12, 20, 15, tzinfo=timezone.utc)
        contests = [{"id": "same-slate", "lock_time": target}, {"id": "one-second-earlier", "lock_time": datetime(2026, 10, 12, 20, 14, 59, tzinfo=timezone.utc)}]
        self.assertEqual([c["id"] for c in eligible_training_contests(contests, target)], ["one-second-earlier"])

    def test_timezone_conversion_cannot_create_false_history(self):
        target = datetime.fromisoformat("2026-10-12T20:15:00+00:00")
        contests = [{"id": "earlier-et", "lock_time": datetime.fromisoformat("2026-10-12T16:14:00-04:00")}, {"id": "later-et", "lock_time": datetime.fromisoformat("2026-10-12T16:16:00-04:00")}]
        self.assertEqual([c["id"] for c in eligible_training_contests(contests, target)], ["earlier-et"])

    def test_walk_forward_never_uses_target_or_future_contests(self):
        contests = [{"id": str(day), "lock_time": datetime(2026, 10, day, 20, 0, tzinfo=timezone.utc)} for day in [10, 11, 12, 13]]
        splits = walk_forward_splits(contests, min_training_contests=2)
        self.assertEqual([s["target"]["id"] for s in splits], ["12", "13"])
        self.assertEqual([c["id"] for c in splits[0]["training"]], ["10", "11"])
        self.assertEqual([c["id"] for c in splits[1]["training"]], ["10", "11", "12"])

    def test_different_games_with_same_lock_are_one_evaluation_batch(self):
        lock = datetime(2026, 10, 12, 20, 15, tzinfo=timezone.utc)
        contests = [
            {"id": "old-game", "game": "SEA-DEN", "lock_time": datetime(2026, 10, 11, 20, 15, tzinfo=timezone.utc)},
            {"id": "buf-lar", "game": "BUF-LAR", "lock_time": lock},
            {"id": "tb-dal", "game": "TB-DAL", "lock_time": lock},
        ]
        batches = walk_forward_batches(contests)
        batch = next(b for b in batches if b["lock_time"] == lock)
        self.assertEqual([c["id"] for c in batch["training"]], ["old-game"])
        self.assertCountEqual([c["id"] for c in batch["targets"]], ["buf-lar", "tb-dal"])

    def test_same_lock_games_become_training_for_later_games(self):
        lock = datetime(2026, 10, 12, 20, 15, tzinfo=timezone.utc)
        later = datetime(2026, 10, 13, 20, 15, tzinfo=timezone.utc)
        contests = [{"id": "old", "lock_time": datetime(2026, 10, 11, 20, 15, tzinfo=timezone.utc)}, {"id": "game-a", "lock_time": lock}, {"id": "game-b", "lock_time": lock}, {"id": "future", "lock_time": later}]
        future_batch = next(b for b in walk_forward_batches(contests) if b["lock_time"] == later)
        self.assertCountEqual([c["id"] for c in future_batch["training"]], ["old", "game-a", "game-b"])

    def test_naive_target_time_is_rejected(self):
        with self.assertRaises(ValueError): eligible_training_contests([], datetime(2026, 10, 12, 20, 15))

    def test_naive_historical_time_is_rejected(self):
        with self.assertRaises(ValueError): eligible_training_contests([{"id": "bad", "lock_time": datetime(2026, 10, 11, 20, 15)}], datetime(2026, 10, 12, 20, 15, tzinfo=timezone.utc))

    def test_missing_historical_lock_time_is_rejected(self):
        with self.assertRaises(KeyError): eligible_training_contests([{"id": "bad"}], datetime(2026, 10, 12, 20, 15, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
