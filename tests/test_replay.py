import json
import unittest

from simurg.core.events import EventType
from simurg.sim import ReplaySession

try:                                   # python -m unittest tests.test_x
    from ._simcache import scenario_result
except ImportError:                    # python -m unittest discover -s tests
    from _simcache import scenario_result


class ReplayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = scenario_result("rta_intervention")
        cls.s = ReplaySession.from_source(cls.result)

    def test_from_json_equals_from_result(self):
        s2 = ReplaySession.from_source(json.dumps(self.result.log))
        self.assertEqual(s2.timeline(), self.s.timeline())

    def test_event_ordering_preserved(self):
        self.assertTrue(self.s.ordering_is_consistent())
        self.assertEqual([e["seq"] for e in self.s.events],
                         [e["seq"] for e in self.result.events])

    def test_histories(self):
        modes = self.s.mode_history()
        self.assertEqual(modes[0][1:3], ("PREFLIGHT", "ARMED"))
        self.assertEqual(modes[-1][2], "DISARMED")
        self.assertEqual(len(modes), self.result.metrics.mode_transitions)
        rta = self.s.rta_history()
        self.assertEqual([r["event"] for r in rta], ["rta_intervention", "rta_recovery"])
        self.assertIn("asiri_yatis", rta[0]["predicted_violations"])
        self.assertEqual(self.s.fault_timeline()[0][1:], ("fault_injected", "F1"))

    def test_state_at_and_series(self):
        st = self.s.state_at(100.0)
        self.assertLessEqual(st["t"], 100.0)
        self.assertIsNone(self.s.state_at(-1.0))
        alt = dict(self.s.series("alt"))
        self.assertGreater(max(alt.values()), 80.0)
        self.assertEqual(self.s.summary()["scenario"], "rta_intervention")

    def test_health_history(self):
        s = ReplaySession.from_source(scenario_result("single_actuator_degradation"))
        h = s.health_history()
        self.assertEqual(h[0]["component_id"], "M2U")
        self.assertEqual(h[0]["state"], "degraded")
        self.assertEqual(len(s.events_of(EventType.FDIR_WARNING)), 1)


if __name__ == "__main__":
    unittest.main()
