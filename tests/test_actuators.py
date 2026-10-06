import unittest

import numpy as np

from simurg.core.errors import InvalidScenarioError
from simurg.sim.actuators import ActuatorCommand, ActuatorMode, ActuatorModel, rpm_from_output
from simurg.sim.faults import Fault, FaultKind

IDS = ("M1", "M2", "S1")


def model(latency=0.0, tau=0.05, dt=0.01):
    return ActuatorModel(IDS, np.array([0.0, 0.0, -1.0]), np.ones(3), np.full(3, tau), latency, dt)


def run(m, u, n):
    st = None
    for k in range(n):
        st = m.step(ActuatorCommand(np.array(u, float), k * 0.01))
    return st


class ActuatorTest(unittest.TestCase):
    def test_first_order_lag_converges(self):
        m = model()
        st = run(m, [1.0, 0.5, -0.5], 5)            # 0,05 s = 1 tau
        self.assertAlmostEqual(st.output[0], 1 - np.exp(-1), places=6)
        st = run(m, [1.0, 0.5, -0.5], 200)
        np.testing.assert_allclose(st.output, [1.0, 0.5, -0.5], atol=1e-6)

    def test_latency_delays_command(self):
        m = model(latency=0.03)
        outs = [m.step(ActuatorCommand(np.array([1.0, 0, 0]), k * 0.01)).output[0] for k in range(5)]
        self.assertEqual(outs[:3], [0.0, 0.0, 0.0])
        self.assertGreater(outs[3], 0.0)

    def test_saturation(self):
        st = run(model(), [3.0, -2.0, -5.0], 300)
        np.testing.assert_allclose(st.output, [1.0, 0.0, -1.0], atol=1e-6)

    def test_degraded_stuck_offline_and_clear(self):
        m = model()
        deg = Fault("d", FaultKind.ACTUATOR_DEGRADED, "actuator:M1", 0.0, severity=0.4)
        stuck = Fault("s", FaultKind.ACTUATOR_STUCK, "actuator:S1", 0.0, params={"position": 0.3})
        off = Fault("o", FaultKind.ACTUATOR_OFFLINE, "actuator:M2", 0.0)
        for f in (deg, stuck, off):
            m.apply_fault(f)
        st = run(m, [1.0, 1.0, -1.0], 300)
        self.assertAlmostEqual(st.output[0], 0.6, places=5)
        self.assertEqual(st.output[1], 0.0)
        self.assertEqual(st.output[2], 0.3)
        self.assertEqual(st.position[2], 0.3)
        np.testing.assert_allclose(st.expected, [1.0, 1.0, -1.0], atol=1e-6)   # nominal model etkilenmez
        self.assertEqual(st.modes, (ActuatorMode.DEGRADED, ActuatorMode.OFFLINE, ActuatorMode.STUCK))
        for f in (deg, stuck, off):
            m.clear_fault(f)
        st = run(m, [1.0, 1.0, -1.0], 300)
        np.testing.assert_allclose(st.output, [1.0, 1.0, -1.0], atol=1e-6)

    def test_unknown_target_and_rpm(self):
        with self.assertRaises(InvalidScenarioError):
            model().apply_fault(Fault("x", FaultKind.ACTUATOR_OFFLINE, "actuator:YOK", 0.0))
        np.testing.assert_allclose(rpm_from_output(np.array([0.25, 1.0]), 7000), [3500, 7000])


if __name__ == "__main__":
    unittest.main()
