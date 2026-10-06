import unittest

import numpy as np

from simurg.config import WEIGHT_N, hover_effectiveness
from simurg.control.allocation import ControlAllocator


class AllocationTest(unittest.TestCase):
    def setUp(self):
        B, lo, hi = hover_effectiveness()
        self.alloc = ControlAllocator(B, lo, hi)

    def test_nominal_hover_is_symmetric(self):
        r = self.alloc.allocate([WEIGHT_N, 0, 0, 0])
        self.assertTrue(r.feasible)
        np.testing.assert_allclose(r.u[:8], r.u[0], atol=1e-9)
        np.testing.assert_allclose(r.u[8:], 0.0, atol=1e-9)

    def test_thrust_to_weight_nominal(self):
        self.assertGreater(self.alloc.hover_margin(WEIGHT_N), 1.55)

    def test_any_single_motor_failure_still_hovers(self):
        for i in range(8):
            h = np.ones(12)
            h[i] = 0.0
            r = self.alloc.allocate([WEIGHT_N, 0, 0, 0], h)
            self.assertTrue(r.feasible, f"motor {i}")
            self.assertEqual(r.u[i], 0.0)
            self.assertGreater(self.alloc.hover_margin(WEIGHT_N, h), 1.15)

    def test_bounds_respected(self):
        h = np.ones(12)
        h[2] = 0.0
        r = self.alloc.allocate([WEIGHT_N * 1.1, 4, -3, 2], h)
        B, lo, hi = hover_effectiveness()
        self.assertTrue(np.all(r.u >= lo - 1e-9) and np.all(r.u <= hi + 1e-9))

    def test_yaw_sacrificed_before_attitude_when_infeasible(self):
        r = self.alloc.allocate([WEIGHT_N * 1.5, 10, 0, 40])
        self.assertFalse(r.feasible)
        self.assertLess(abs(r.error[1]), 0.5)          # roll korunur
        self.assertGreater(abs(r.error[3]), abs(r.error[1]))

    def test_same_tip_double_failure_detected_as_not_hoverable(self):
        h = np.ones(12)
        h[0] = h[4] = 0.0   # M1U + M1L: aynı uç
        self.assertLess(self.alloc.hover_margin(WEIGHT_N, h), 1.0)


if __name__ == "__main__":
    unittest.main()
