#!/usr/bin/env python3
"""Unit tests for deadman.decide() — run: python3 test_deadman.py"""
import unittest
from deadman import decide, decide_tick

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

class DecideTick(unittest.TestCase):
    """decide_tick(event, tick_seen, dispatch_age_min, since_tick_alert_min, stale_after, repeat)
    -> (tick_seen, action). The Cloudflare tick (workflow_dispatch every 10 min) exists because
    GitHub drops most schedule runs; if the tick dies (PAT expired, worker gone) the switch
    silently falls back to the 2-5 h cadence. Self-arming: nothing fires until one dispatch
    run has ever been seen."""
    S, R = 60, 1440

    def test_never_seen_never_alerts(self):
        self.assertEqual(decide_tick("schedule", False, 500, None, self.S, self.R), (False, None))

    def test_dispatch_arms(self):
        self.assertEqual(decide_tick("workflow_dispatch", False, None, None, self.S, self.R), (True, None))

    def test_recent_dispatch_quiet(self):
        self.assertEqual(decide_tick("schedule", True, 30, None, self.S, self.R), (True, None))

    def test_stale_dispatch_alerts_once(self):
        self.assertEqual(decide_tick("schedule", True, 90, None, self.S, self.R), (True, "tick_alert"))
        self.assertEqual(decide_tick("schedule", True, 90, 60, self.S, self.R), (True, None))
        self.assertEqual(decide_tick("schedule", True, 900, 1500, self.S, self.R), (True, "tick_alert"))

    def test_dispatch_after_alert_recovers(self):
        self.assertEqual(decide_tick("workflow_dispatch", True, None, 200, self.S, self.R), (True, "tick_recovered"))

    def test_unknown_age_is_not_an_alert(self):
        self.assertEqual(decide_tick("schedule", True, None, None, self.S, self.R), (True, None))


if __name__ == "__main__":
    unittest.main(verbosity=1)
