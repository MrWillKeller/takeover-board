#!/usr/bin/env python3
"""Unit tests for deadman.decide() — run: python3 test_deadman.py"""
import unittest
from deadman import decide

T, R = 50, 360  # threshold min, repeat min

class Decide(unittest.TestCase):
    def test_fresh_stays_quiet(self):
        self.assertEqual(decide(age_min=12, state="fresh", since_alert_min=None, threshold=T, repeat=R), ("fresh", None))

    def test_just_under_threshold_is_fresh(self):
        self.assertEqual(decide(49.9, "fresh", None, T, R), ("fresh", None))

    def test_crossing_threshold_alerts_once(self):
        self.assertEqual(decide(50.1, "fresh", None, T, R), ("stale", "alert"))

    def test_stale_within_repeat_window_is_silent(self):
        self.assertEqual(decide(120, "stale", 70, T, R), ("stale", None))

    def test_stale_past_repeat_window_reminds(self):
        self.assertEqual(decide(500, "stale", 361, T, R), ("stale", "remind"))

    def test_recovery_sends_once(self):
        self.assertEqual(decide(3, "stale", 200, T, R), ("fresh", "recovered"))

    def test_unknown_state_treated_as_fresh(self):
        self.assertEqual(decide(3, "", None, T, R), ("fresh", None))
        self.assertEqual(decide(90, "", None, T, R), ("stale", "alert"))

if __name__ == "__main__":
    unittest.main(verbosity=1)
