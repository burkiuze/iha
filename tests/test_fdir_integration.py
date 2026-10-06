import unittest

import numpy as np

from simurg.core.events import EventType
from simurg.core.types import HealthState
from simurg.fdir.monitor import MotorHealthMonitor, SurfaceMonitor

try:                                   # python -m unittest tests.test_x
    from ._simcache import scenario_result
except ImportError:                    # python -m unittest discover -s tests
    from _simcache import scenario_result


class ReportFormatTest(unittest.TestCase):
    def test_reports_standard_format_and_unknown_when_unobserved(self):
        m = MotorHealthMonitor(n=3, min_observable_abs=1000.0)
        cmd = np.array([6000.0, 6000.0, 500.0])       # 3. motor gözlenemez
        meas = cmd.copy()
        meas[1] = 0.0
        m.update(cmd, meas)
        r = m.reports(2.0, ["A", "B", "C"])
        self.assertEqual([x.component_id for x in r], ["A", "B", "C"])
        self.assertEqual([x.state for x in r],
                         [HealthState.NOMINAL, HealthState.FAILED, HealthState.UNKNOWN])
        self.assertEqual(r[1].health_score, 0.0)
        self.assertEqual(r[1].reason, "devir_yok")
        self.assertEqual(r[0].timestamp, 2.0)
        self.assertEqual(set(r[0].to_dict()), {"component_id", "state", "health_score",
                                               "confidence", "reason", "timestamp"})

    def test_surface_monitor_detects_stuck_surface(self):
        s = SurfaceMonitor(n=2, persistence=5)
        for _ in range(4):
            s.update([0.5, 0.5], [0.5, 0.0])
        self.assertFalse(s.failed[1])
        s.update([0.5, 0.5], [0.5, 0.0])
        self.assertTrue(s.failed[1])
        self.assertEqual(s.reports(1.0)[1].state, HealthState.FAILED)


class FdirInSimulationTest(unittest.TestCase):
    def test_degraded_motor_detected_and_fed_to_allocation(self):
        r = scenario_result("single_actuator_degradation")
        self.assertTrue(r.passed, r.expectation_failures)
        warn = [e for e in r.events if e["type"] == EventType.FDIR_WARNING.value]
        self.assertEqual([e["data"]["component_id"] for e in warn], ["M2U"])
        self.assertLess(r.metrics.detection_latency_s["F1"], 1.0)
        idx = r.log["meta"]["actuator_ids"].index("M2U")
        h = r.final_state.actuator_health[idx]
        self.assertAlmostEqual(h, 0.7, delta=0.05)         # itki oranı ~ 1 - şiddet
        others = np.delete(r.final_state.actuator_health, idx)
        np.testing.assert_allclose(others, 1.0)

    def test_no_false_alarms_in_nominal_flight(self):
        r = scenario_result("nominal")
        self.assertFalse([e for e in r.events if e["type"].startswith("fdir")])


if __name__ == "__main__":
    unittest.main()
