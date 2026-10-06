import json
import unittest

from simurg.core.events import EventType
from simurg.safety.rta import (Command, EnvelopeState, KinematicPredictor, RuntimeAssurance,
                               Source)

try:                                   # python -m unittest tests.test_x
    from ._simcache import scenario_result
except ImportError:                    # python -m unittest discover -s tests
    from _simcache import scenario_result


def cruise(**kw):
    s = dict(alt_agl_m=150, airspeed_mps=28, bank_deg=0, pitch_deg=2, climb_mps=0,
             fence_dist_m=2000, fence_closing_mps=0)
    s.update(kw)
    return EnvelopeState(**s)


SAFE = Command(0, 3, 26)


class DecisionApiTest(unittest.TestCase):
    def test_decision_metadata_on_intervention(self):
        rta = RuntimeAssurance()
        d = rta.decide(cruise(), Command(70, 2, 28), SAFE, timestamp=12.5)
        self.assertIs(d.selected_source, Source.SAFETY)
        self.assertTrue(d.switched)
        self.assertIn("asiri_yatis", d.predicted_violations)
        self.assertEqual(d.current_violations, ())
        self.assertFalse(d.latched)
        self.assertEqual((d.prediction_horizon_s, d.timestamp), (3.0, 12.5))
        self.assertIs(d.command, SAFE)
        json.dumps(d.to_dict())

    def test_select_is_backward_compatible_with_decide(self):
        a, b = RuntimeAssurance(), RuntimeAssurance()
        for cmd in (Command(10, 2, 28), Command(70, 2, 28), Command(10, 2, 28)):
            c1, s1 = a.select(cruise(), cmd, SAFE)
            d = b.decide(cruise(), cmd, SAFE)
            self.assertEqual((c1, s1), (d.command, d.selected_source))

    def test_latch_metadata(self):
        rta = RuntimeAssurance()
        d = rta.decide(cruise(alt_agl_m=10), Command(0, 2, 28), SAFE)
        self.assertTrue(d.latched)
        self.assertIn("alcak_irtifa", d.current_violations)
        d = rta.decide(cruise(), Command(0, 2, 28), SAFE)
        self.assertTrue(d.latched)
        self.assertEqual(d.reasons[0], "kilitli")
        self.assertFalse(d.switched)

    def test_recovery_requires_hysteresis(self):
        rta = RuntimeAssurance(recovery_cycles=5)
        rta.decide(cruise(), Command(70, 2, 28), SAFE)
        sources = [rta.decide(cruise(), Command(10, 2, 28), SAFE).selected_source
                   for _ in range(5)]
        self.assertEqual(sources[:4], [Source.SAFETY] * 4)
        self.assertIs(sources[4], Source.ADVANCED)

    def test_custom_predictor_injection(self):
        class Pessimist:
            def predict(self, s, c, h):
                return cruise(alt_agl_m=0)
        rta = RuntimeAssurance(predictor=Pessimist())
        d = rta.decide(cruise(), Command(0, 2, 28), SAFE)
        self.assertIn("alcak_irtifa", d.predicted_violations)
        self.assertIs(d.selected_source, Source.SAFETY)
        self.assertIsInstance(RuntimeAssurance().predictor, KinematicPredictor)

    def test_envelope_margin(self):
        rta = RuntimeAssurance()
        self.assertGreater(rta.soft.margin(cruise()), 0)
        self.assertLess(rta.soft.margin(cruise(bank_deg=60)), 0)


class RtaInSimulationTest(unittest.TestCase):
    def test_controller_fault_triggers_intervention_then_recovery(self):
        r = scenario_result("rta_intervention")
        self.assertTrue(r.passed, r.expectation_failures)
        ev = r.events
        inj = next(e for e in ev if e["type"] == EventType.FAULT_INJECTED.value)
        itv = next(e for e in ev if e["type"] == EventType.RTA_INTERVENTION.value)
        rec = next(e for e in ev if e["type"] == EventType.RTA_RECOVERY.value)
        self.assertLessEqual(inj["seq"], itv["seq"])
        self.assertLess(itv["time_s"] - inj["time_s"], 0.1)
        self.assertIn("asiri_yatis", itv["data"]["predicted_violations"])
        clear = next(e for e in ev if e["type"] == EventType.FAULT_CLEARED.value)
        # histerezis: temizlendiği adım dahil 50 çevrim (49 aralık x 0,02 s)
        self.assertGreaterEqual(rec["time_s"] - clear["time_s"], 49 * 0.02 - 1e-6)
        self.assertFalse(r.metrics.rta_latched)
        self.assertLess(r.metrics.max_attitude_error_deg, 60.0)

    def test_nominal_flight_has_no_rta_intervention(self):
        r = scenario_result("nominal")
        self.assertEqual(r.metrics.rta_interventions, 0)
        self.assertGreater(r.metrics.min_safety_margin, 0.1)


if __name__ == "__main__":
    unittest.main()
