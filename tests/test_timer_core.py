"""python -m unittest discover -s tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from timer_core import (GameClock, TimerModel, apply_haste, rank_from_level,
                        level_scaled, teleport_cd, fmt_countdown, fmt_clock)


class FakeMono:
    def __init__(self): self.t = 100.0
    def __call__(self): return self.t


class TestGameClock(unittest.TestCase):
    def test_unsynced_is_zero(self):
        self.assertEqual(GameClock().now(), 0.0)

    def test_interpolates_between_polls(self):
        mono = FakeMono()
        c = GameClock(monotonic=mono)
        c.sync(600.0)
        mono.t += 1.5
        self.assertAlmostEqual(c.now(), 601.5)

    def test_extrapolation_is_capped(self):
        # Game paused / API stalled: don't run ahead forever.
        mono = FakeMono()
        c = GameClock(max_extrapolate=3.0, monotonic=mono)
        c.sync(600.0)
        mono.t += 30
        self.assertAlmostEqual(c.now(), 603.0)

    def test_resync_corrects(self):
        mono = FakeMono()
        c = GameClock(monotonic=mono)
        c.sync(600.0)
        mono.t += 2
        c.sync(601.0)  # game was paused for 1s
        self.assertAlmostEqual(c.now(), 601.0)


class TestTimerModel(unittest.TestCase):
    def test_start_remaining_ready(self):
        m = TimerModel()
        k = ("Darius", "S1")
        m.start(k, 300, used_at=597)
        self.assertTrue(m.is_active(k))
        self.assertAlmostEqual(m.ready_at(k), 897)
        self.assertAlmostEqual(m.remaining(k, 600), 297)

    def test_adjust_and_reset(self):
        m = TimerModel()
        k = ("Darius", "R")
        m.start(k, 100, used_at=0)
        m.adjust(k, -5)
        self.assertAlmostEqual(m.ready_at(k), 95)
        m.reset(k)
        self.assertFalse(m.is_active(k))
        self.assertIsNone(m.remaining(k, 0))
        m.adjust(k, 5)  # no-op on idle key
        self.assertFalse(m.is_active(k))

    def test_keys_independent(self):
        m = TimerModel()
        m.start(("A", "S1"), 300, 0)
        m.start(("A", "UTP"), 390, 0)
        m.reset(("A", "S1"))
        self.assertTrue(m.is_active(("A", "UTP")))


class TestCooldowns(unittest.TestCase):
    def test_haste_flash_cosmic(self):
        # 300 / 1.18 = 254.24 (matches in-game tab tooltip)
        self.assertAlmostEqual(apply_haste(300, 18), 254.237, places=2)
        self.assertEqual(apply_haste(300, 0), 300.0)

    def test_rank_from_level(self):
        self.assertEqual([rank_from_level(l) for l in (1, 5, 6, 10, 11, 15, 16, 18)],
                         [0, 0, 1, 1, 2, 2, 3, 3])
        self.assertEqual(rank_from_level(None), 0)

    def test_level_scaled_endpoints_and_clamp(self):
        self.assertEqual(level_scaled(330, 240, 1), 330)
        self.assertEqual(level_scaled(330, 240, 18), 240)
        self.assertEqual(level_scaled(330, 240, 25), 240)
        self.assertEqual(level_scaled(330, 240, 0), 330)

    def test_teleport(self):
        self.assertEqual(teleport_cd(599, 9, False), 360)
        self.assertEqual(teleport_cd(600, 1, False), 330)
        self.assertEqual(teleport_cd(600, 18, False), 240)
        self.assertEqual(teleport_cd(600, 1, True), 300)
        self.assertEqual(teleport_cd(600, 18, True), 210)


class TestFormat(unittest.TestCase):
    def test_countdown(self):
        self.assertEqual(fmt_countdown(254.2), "4:15")
        self.assertEqual(fmt_countdown(59.1), "1:00")
        self.assertEqual(fmt_countdown(45), "45")
        self.assertEqual(fmt_countdown(0.2), "1")
        self.assertEqual(fmt_countdown(-3), "0")

    def test_clock(self):
        self.assertEqual(fmt_clock(865.0), "14:25")
        self.assertEqual(fmt_clock(864.1), "14:25")
        self.assertEqual(fmt_clock(3725), "62:05")


if __name__ == "__main__":
    unittest.main()
