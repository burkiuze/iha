import unittest

import numpy as np

from simurg.fdir.monitor import Health, MotorHealthMonitor, TripleLaneVoter


class FdirTest(unittest.TestCase):
    def test_nominal_noise_no_alarm(self):
        rng = np.random.default_rng(1)
        m = MotorHealthMonitor()
        cmd = np.full(8, 6000.0)
        for _ in range(2000):
            m.update(cmd, cmd * (1 + rng.normal(0, 0.01, 8)))
        self.assertTrue(all(s is Health.OK for s in m.state))

    def test_dead_motor_immediate(self):
        m = MotorHealthMonitor()
        cmd = np.full(8, 6000.0)
        meas = cmd.copy()
        meas[3] = 0.0
        h = m.update(cmd, meas)
        self.assertEqual(h[3], 0.0)
        self.assertIs(m.state[3], Health.FAILED)

    def test_degraded_prop_detected_with_partial_health(self):
        m = MotorHealthMonitor()
        cmd = np.full(8, 6000.0)
        meas = cmd.copy()
        meas[5] *= 0.92          # %8 devir kaybı (ör. kırık pervane ucu)
        for _ in range(5000):    # uzun süre: kısmi hasar arızaya tırmanmamalı
            h = m.update(cmd, meas)
        self.assertIs(m.state[5], Health.DEGRADED)
        self.assertAlmostEqual(h[5], 0.92 ** 2, places=3)
        self.assertLess(h[5], 1.0)
        self.assertGreater(h[5], 0.0)

    def test_gradual_loss_escalates_to_failed(self):
        m = MotorHealthMonitor()
        cmd = np.full(8, 6000.0)
        for k in range(400):
            meas = cmd.copy()
            meas[2] *= max(1.0 - k * 0.002, 0.4)   # rulman bozulması
            m.update(cmd, meas)
        self.assertIs(m.state[2], Health.FAILED)

    def test_voter_isolates_drifting_lane(self):
        v = TripleLaneVoter(tol=0.05, persistence=3)
        for k in range(3):
            out = v.vote([0.0], [0.01], [0.5])
            self.assertAlmostEqual(float(out[0]), 0.01)   # orta değer
        self.assertEqual(v.isolated, [False, False, True])
        out = v.vote([0.0], [0.01], [0.5])
        self.assertAlmostEqual(float(out[0]), 0.005)      # kalan iki şeridin ortalaması
        self.assertFalse(v.disagree([0.0], [0.01], [9.0]))
        self.assertTrue(v.disagree([0.0], [0.2], [9.0]))


if __name__ == "__main__":
    unittest.main()
