import unittest
from datetime import datetime, timezone


def eligible_training_contests(contests, target_lock):
    """Only contests locked strictly before the target can teach its field model."""
    target = target_lock.astimezone(timezone.utc)
    return [contest for contest in contests if contest["lock_time"].astimezone(timezone.utc) < target]


class DKShowdownTemporalLearningTests(unittest.TestCase):
    def test_future_contest_is_excluded_from_training(self):
        target = datetime(2026, 10, 12, 20, 15, tzinfo=timezone.utc)
        contests = [
            {"id": "earlier", "lock_time": datetime(2026, 10, 11, 20, 15, tzinfo=timezone.utc)},
            {"id": "later", "lock_time": datetime(2026, 10, 15, 20, 15, tzinfo=timezone.utc)},
        ]
        eligible = eligible_training_contests(contests, target)
        self.assertEqual([contest["id"] for contest in eligible], ["earlier"])

    def test_same_lock_time_is_not_training_data(self):
        target = datetime(2026, 10, 12, 20, 15, tzinfo=timezone.utc)
        contests = [
            {"id": "same-slate", "lock_time": target},
            {"id": "one-second-earlier", "lock_time": datetime(2026, 10, 12, 20, 14, 59, tzinfo=timezone.utc)},
        ]
        eligible = eligible_training_contests(contests, target)
        self.assertEqual([contest["id"] for contest in eligible], ["one-second-earlier"])

    def test_timezone_conversion_cannot_create_false_history(self):
        target = datetime.fromisoformat("2026-10-12T20:15:00+00:00")
        contests = [
            {"id": "earlier-et", "lock_time": datetime.fromisoformat("2026-10-12T16:14:00-04:00")},
            {"id": "later-et", "lock_time": datetime.fromisoformat("2026-10-12T16:16:00-04:00")},
        ]
        eligible = eligible_training_contests(contests, target)
        self.assertEqual([contest["id"] for contest in eligible], ["earlier-et"])


if __name__ == "__main__":
    unittest.main()
