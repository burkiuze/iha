import unittest

from simurg.sim.metrics import MetricsAccumulator, compute_metrics, detection_latencies

try:                                   # python -m unittest tests.test_x
    from ._simcache import scenario_result
except ImportError:                    # python -m unittest discover -s tests
    from _simcache import scenario_result


def ev(seq, t, typ, **data):
    return {"seq": seq, "time_s": t, "type": typ, "source": "x", "message": "", "data": data}


class MetricsUnitTest(unittest.TestCase):
    def test_detection_latency_matching_rules(self):
        faults = [{"id": "A", "target": "actuator:M1U"}, {"id": "B", "target": "sensor:GNSS"},
                  {"id": "C", "target": "link:c2"}, {"id": "D", "target": "actuator:M2U"}]
        events = [ev(0, 9.0, "fdir_warning", component_id="M1U"),     # aktivasyondan önce
                  ev(1, 10.5, "fdir_warning", component_id="M2U"),
                  ev(2, 10.7, "fdir_warning", component_id="M1U"),
                  ev(3, 20.0, "nav_source_rejected", source="GNSS"),
                  ev(4, 31.0, "link_lost")]
        lat = detection_latencies(events, faults, {"A": 10.0, "B": 19.8, "C": 31.0, "D": 50.0})
        self.assertEqual(lat, {"A": 0.7, "B": 0.2, "C": 0.0})        # D tespit edilmedi

    def test_compute_counts(self):
        acc = MetricsAccumulator(ticks=100, saturated_ticks=25, fw_ticks=10,
                                 min_envelope_margin=0.3, energy_consumed_j=7200.0)
        events = [ev(0, 1, "rta_intervention"), ev(1, 2, "mode_transition"),
                  ev(2, 3, "nav_integrity_lost"), ev(3, 4, "impact")]
        m = compute_metrics(events, acc, 12.0, "VTOL_LAND", False, [], {}, 100.0, 70.0)
        self.assertEqual((m.rta_interventions, m.mode_transitions, m.nav_integrity_losses),
                         (1, 1, 1))
        self.assertTrue(m.impact)
        self.assertEqual((m.actuator_saturation_pct, m.energy_consumed_wh), (25.0, 2.0))
        self.assertEqual(m.min_safety_margin, 0.3)
        self.assertIsNone(m.max_detection_latency_s)


class MetricsInSimulationTest(unittest.TestCase):
    def test_combined_scenario_metrics(self):
        m = scenario_result("combined_degraded").metrics
        self.assertEqual((m.fault_count, m.faults_detected), (3, 3))
        self.assertLess(m.max_detection_latency_s, 1.0)
        self.assertGreater(m.energy_consumed_wh, 50.0)
        self.assertTrue(0.0 <= m.actuator_saturation_pct <= 100.0)
        self.assertGreater(m.remaining_usable_energy_wh, 0.0)
        self.assertEqual(m.nav_sources_rejected, 1)


if __name__ == "__main__":
    unittest.main()
