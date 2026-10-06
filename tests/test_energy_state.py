import unittest

from simurg.core.events import EventType
from simurg.power.energy_manager import EnergyManager

try:                                   # python -m unittest tests.test_x
    from ._simcache import scenario_result
except ImportError:                    # python -m unittest discover -s tests
    from _simcache import scenario_result


class EnergyStateTest(unittest.TestCase):
    def test_state_fields_si_units(self):
        em = EnergyManager()
        em.step(0.1, 590.0, solar_w=50.0)
        s = em.state()
        self.assertAlmostEqual(s.available_energy_j, em.usable_energy_wh() * 3600.0)
        self.assertAlmostEqual(s.reserve_energy_j, 0.2 * 389.0 * 0.97 * 3600.0, places=3)
        self.assertEqual((s.power_demand_w, s.solar_input_w, s.health), (590.0, 50.0, 1.0))
        self.assertTrue(s.fuel_cell_available)

    def test_degradation_propagates_to_reserve_and_rth(self):
        em = EnergyManager()
        ok_before = em.return_home_feasible(20_000, 25, 590)
        em.h2_wh = 0.0
        e0 = em.state().available_energy_j
        em.batt_capacity_scale = 0.5
        s = em.state()
        self.assertAlmostEqual(s.available_energy_j, e0 * 0.5, places=3)
        self.assertEqual(s.health, 0.5)
        self.assertFalse(s.fuel_cell_available)
        self.assertTrue(ok_before)
        self.assertFalse(em.return_home_feasible(20_000, 25, 590))

    def test_degradation_model_injection(self):
        class Aging:
            def __init__(self):
                self.calls = 0

            def update(self, m, dt):
                self.calls += 1
                m.fc_power_scale = 0.5

        a = Aging()
        em = EnergyManager(degradation=a)
        for _ in range(500):
            em.step(0.1, 3000.0)
        self.assertEqual(a.calls, 500)
        self.assertLessEqual(em.fc_w, 400.0 + 1e-9)

    def test_power_limit_causes_unmet_power(self):
        em = EnergyManager()
        em.batt_discharge_scale = em.sc_power_scale = 0.1
        s = em.step(0.02, 4000.0)
        self.assertGreater(s.unmet_w, 0.0)
        self.assertAlmostEqual(s.bus_balance_w, 0.0, places=6)


class EnergyInSimulationTest(unittest.TestCase):
    def test_reserve_warning_aborts_mission_and_lands(self):
        r = scenario_result("energy_reserve_warning")
        self.assertTrue(r.passed, r.expectation_failures)
        types = [e["type"] for e in r.events]
        w = types.index(EventType.ENERGY_WARNING.value)
        self.assertEqual(types[w + 1], EventType.MISSION_ABORT.value)
        ret = next(e for e in r.events if e["type"] == "mode_transition"
                   and e["data"]["target"] == "RETURN")
        self.assertEqual(ret["data"]["reason"], "enerji_uyarisi")
        self.assertGreater(r.metrics.remaining_reserve_wh, 0.0)


if __name__ == "__main__":
    unittest.main()
