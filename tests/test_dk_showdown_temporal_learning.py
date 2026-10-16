import unittest
from datetime import datetime, timezone

from dk_showdown_history import eligible_training_contests, walk_forward_splits


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
        for split in splits:
            target_time = split["target"]["lock_time"]
            self.assertTrue(all(c["lock_time"] < target_time for c in split["training"]))

    def test_walk_forward_same_lock_contests_cannot_train_each_other(self):
        lock = datetime(2026, 10, 12, 20, 0, tzinfo=timezone.utc)
        contests = [{"id": "old", "lock_time": datetime(2026, 10, 11, 20, 0, tzinfo=timezone.utc)}, {"id": "a", "lock_time": lock}, {"id": "b", "lock_time": lock}]
        splits = walk_forward_splits(contests)
        same_lock = [s for s in splits if s["target"]["id"] in {"a", "b"}]
        self.assertEqual(len(same_lock), 2)
        for split in same_lock:
            self.assertEqual([c["id"] for c in split["training"]], ["old"])

    def test_naive_target_time_is_rejected(self):
        with self.assertRaises(ValueError): eligible_training_contests([], datetime(2026, 10, 12, 20, 15))

    def test_naive_historical_time_is_rejected(self):
        with self.assertRaises(ValueError): eligible_training_contests([{"id": "bad", "lock_time": datetime(2026, 10, 11, 20, 15)}], datetime(2026, 10, 12, 20, 15, tzinfo=timezone.utc))

    def test_missing_historical_lock_time_is_rejected(self):
        with self.assertRaises(KeyError): eligible_training_contests([{"id": "bad"}], datetime(2026, 10, 12, 20, 15, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
