import unittest

import numpy as np

from simurg.core.config import EnvironmentConfig
from simurg.core.errors import InvalidScenarioError
from simurg.sim.environment import ConstantEnvironment, ScriptedEnvironment


class EnvironmentTest(unittest.TestCase):
    def test_constant(self):
        e = ConstantEnvironment(EnvironmentConfig(wind_ned_mps=(3.0, -1.0, 0.0)))
        e.bind_rng(np.random.default_rng(0))
        s = e.update(0.0, 0.02, np.zeros(3))
        np.testing.assert_allclose(s.wind_ned, [3.0, -1.0, 0.0])
        self.assertAlmostEqual(s.density, 1.225)

    def test_scripted_interpolation_and_hold(self):
        e = ScriptedEnvironment([(0.0, (0.0, 0.0, 0.0)), (10.0, (10.0, 0.0, 0.0))])
        e.bind_rng(np.random.default_rng(0))
        self.assertAlmostEqual(e.update(5.0, 0.02, np.zeros(3)).wind_ned[0], 5.0)
        self.assertAlmostEqual(e.update(50.0, 0.02, np.zeros(3)).wind_ned[0], 10.0)

    def test_turbulence_deterministic_with_seed(self):
        def series(seed):
            e = ConstantEnvironment(EnvironmentConfig(turbulence_std_mps=1.0))
            e.bind_rng(np.random.default_rng(seed))
            return np.array([e.update(i * 0.02, 0.02, np.zeros(3)).wind_ned for i in range(200)])
        np.testing.assert_array_equal(series(4), series(4))
        self.assertFalse(np.allclose(series(4), series(5)))
        self.assertTrue(0.2 < float(np.std(series(4))) < 2.0)

    def test_invalid_keyframes(self):
        with self.assertRaises(InvalidScenarioError):
            ScriptedEnvironment([])
        with self.assertRaises(InvalidScenarioError):
            ScriptedEnvironment([(5.0, (0, 0, 0)), (1.0, (0, 0, 0))])


if __name__ == "__main__":
    unittest.main()
