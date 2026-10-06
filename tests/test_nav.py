import unittest

import numpy as np

from simurg.nav.integrity import IntegrityMonitor, PositionFix, chi2_quantile


def fixes(spoof=np.zeros(2)):
    rng = np.random.default_rng(7)
    truth = np.array([1000.0, 2000.0])
    spec = {"GNSS": 3.0, "VIO": 8.0, "TRN": 15.0, "MAGNAV": 25.0}
    out = []
    for name, sigma in spec.items():
        p = truth + rng.normal(0, sigma, 2) + (spoof if name == "GNSS" else 0)
        out.append(PositionFix(name, p, np.eye(2) * sigma ** 2))
    return truth, out


class NavTest(unittest.TestCase):
    def test_chi2_approximation(self):
        self.assertAlmostEqual(chi2_quantile(0.95, 2), 5.99, delta=0.15)
        self.assertAlmostEqual(chi2_quantile(0.99, 6), 16.81, delta=0.3)

    def test_nominal_all_used(self):
        truth, f = fixes()
        r = IntegrityMonitor().evaluate(f)
        self.assertEqual(r.excluded, [])
        self.assertTrue(r.integrity_ok)
        self.assertLess(np.linalg.norm(r.position - truth), 10)

    def test_gnss_spoof_excluded(self):
        truth, f = fixes(spoof=np.array([180.0, -120.0]))
        r = IntegrityMonitor().evaluate(f)
        self.assertEqual(r.excluded, ["GNSS"])
        self.assertLess(np.linalg.norm(r.position - truth), 30)

    def test_large_protection_level_flags_integrity(self):
        _, f = fixes()
        r = IntegrityMonitor(alert_limit_m=5.0).evaluate(f[1:])
        self.assertFalse(r.integrity_ok)


if __name__ == "__main__":
    unittest.main()
