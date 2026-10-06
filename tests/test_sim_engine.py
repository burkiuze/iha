import unittest
from dataclasses import replace

import numpy as np

from simurg.core.errors import InvalidScenarioError
from simurg.sim import (SCENARIOS, TICK_ORDER, MissionProfile, Scenario, SimulationEngine,
                        get_scenario)

try:                                   # python -m unittest tests.test_x
    from ._simcache import scenario_result
except ImportError:                    # python -m unittest discover -s tests
    from _simcache import scenario_result


def short(name, seed=0, duration=70.0):
    return replace(get_scenario(name, seed), duration_s=duration)


class EngineBasicsTest(unittest.TestCase):
    def test_tick_order_documented_and_fixed(self):
        self.assertEqual(TICK_ORDER, (
            "scenario_events", "environment", "sensors", "navigation", "health", "proposals",
            "rta", "allocation", "actuators", "dynamics", "power", "contingency", "logging",
            "metrics"))

    def test_invalid_scenarios_rejected(self):
        with self.assertRaises(InvalidScenarioError):
            SimulationEngine(Scenario("x", duration_s=-1))
        with self.assertRaises(InvalidScenarioError):
            SimulationEngine(Scenario("x", mission=MissionProfile(waypoints=((9000.0, 0.0),))))
        with self.assertRaises(InvalidScenarioError):
            SimulationEngine(Scenario("x", mission=MissionProfile(takeoff_alt_m=20.0)))
        with self.assertRaises(InvalidScenarioError):
            get_scenario("yok")

    def test_takeoff_and_transition_physics(self):
        r = scenario_result("nominal")
        self.assertEqual(r.metrics.transitions_completed, 2)      # ileri + geri
        self.assertLess(r.metrics.max_transition_altitude_loss_m, 5.0)
        self.assertLess(float(np.linalg.norm(r.final_state.position_ned[:2])), 5.0)  # eve iniş
        self.assertTrue(r.final_state.landed)
        td = next(e for e in r.events if e["type"] == "touchdown")
        self.assertLess(td["data"]["vertical_speed_mps"], 1.5)


class DeterminismTest(unittest.TestCase):
    def test_same_seed_same_result(self):
        a = SimulationEngine(short("combined_degraded", 7)).run()
        b = SimulationEngine(short("combined_degraded", 7)).run()
        np.testing.assert_array_equal(a.final_state.position_ned, b.final_state.position_ned)
        np.testing.assert_array_equal(a.final_state.quaternion, b.final_state.quaternion)
        self.assertEqual(a.events, b.events)
        self.assertEqual(a.metrics, b.metrics)
        self.assertEqual(a.log, b.log)

    def test_different_seed_different_noise(self):
        a = SimulationEngine(short("combined_degraded", 7, 30.0)).run()
        b = SimulationEngine(short("combined_degraded", 8, 30.0)).run()
        self.assertFalse(np.array_equal(a.final_state.position_ned, b.final_state.position_ned))

    def test_fault_activation_reproducible(self):
        e1 = SimulationEngine(short("combined_degraded", 1))
        e2 = SimulationEngine(short("combined_degraded", 2))
        e1.run(), e2.run()
        self.assertEqual(e1.injector.activation_times, e2.injector.activation_times)


class ScenarioLibraryTest(unittest.TestCase):
    """Her hazır senaryo beklenen güvenlik sonuçlarını üretmeli."""

    def test_all_library_scenarios_meet_expectations(self):
        for name in SCENARIOS:
            with self.subTest(scenario=name):
                r = scenario_result(name)
                self.assertTrue(r.passed, r.expectation_failures)
                self.assertFalse(r.metrics.impact)


if __name__ == "__main__":
    unittest.main()
