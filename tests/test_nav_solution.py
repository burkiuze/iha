import unittest

import numpy as np

from simurg.core.types import SensorMeasurement
from simurg.nav.providers import NavigationSystem


class FakeProvider:
    def __init__(self, sid, sigma, offset=(0.0, 0.0), valid=True):
        self.source_id, self.sigma, self.offset, self.valid = sid, sigma, np.array(offset), valid
        self.truth = np.array([100.0, 200.0])

    def provide(self, t):
        return SensorMeasurement(self.source_id, t, self.truth + self.offset,
                                 np.eye(2) * self.sigma ** 2, self.valid)


def system(*providers):
    return NavigationSystem(list(providers))


class NavigationSolutionTest(unittest.TestCase):
    def test_nominal_solution_fields(self):
        s = system(FakeProvider("GNSS", 3), FakeProvider("VIO", 8), FakeProvider("TRN", 15))
        sol = s.update(1.0, 120.0, np.array([20.0, 0, -1]))
        self.assertTrue(sol.integrity_ok)
        np.testing.assert_allclose(sol.position_ned, [100, 200, -120])
        self.assertEqual(sol.sources_used, ("GNSS", "VIO", "TRN"))
        self.assertGreater(sol.confidence, 0.5)
        self.assertEqual(sol.timestamp, 1.0)

    def test_biased_source_rejected(self):
        s = system(FakeProvider("GNSS", 3, (180, -120)), FakeProvider("VIO", 8),
                   FakeProvider("TRN", 15), FakeProvider("MAGNAV", 25))
        sol = s.update(0.0, 100.0, np.zeros(3))
        self.assertEqual(sol.sources_rejected, ("GNSS",))
        self.assertTrue(sol.integrity_ok)

    def test_single_source_cannot_be_verified(self):
        s = system(FakeProvider("GNSS", 3), FakeProvider("VIO", 8, valid=False))
        sol = s.update(0.0, 100.0, np.zeros(3))
        self.assertFalse(sol.integrity_ok)
        self.assertEqual(sol.sources_unavailable, ("VIO",))
        self.assertLess(sol.confidence, 0.5)

    def test_no_source_inertial_propagation_with_growing_pl(self):
        a, b = FakeProvider("GNSS", 3), FakeProvider("VIO", 8)
        s = system(a, b)
        s.update(0.0, 100.0, np.array([10.0, 0, 0]))
        a.valid = b.valid = False
        sol1 = s.update(1.0, 100.0, np.array([10.0, 0, 0]))
        sol2 = s.update(2.0, 100.0, np.array([10.0, 0, 0]))
        self.assertFalse(sol2.integrity_ok)
        self.assertAlmostEqual(sol2.position_ned[0], 120.0)
        self.assertGreater(sol2.protection_level_m, sol1.protection_level_m)


if __name__ == "__main__":
    unittest.main()
