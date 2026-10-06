"""Fail-safe: bilinmeyen durum otomatik olarak sağlıklı kabul edilmez."""

import math
import unittest
from dataclasses import replace

import numpy as np

from simurg.aero import AnalyticAeroModel
from simurg.core.config import SimulationConfig, VehicleConfig
from simurg.core.errors import ConfigurationError, SimulationError
from simurg.core.events import EventType
from simurg.core.types import SensorMeasurement
from simurg.nav.providers import NavigationSystem
from simurg.power.reserve import ReserveMonitor
from simurg.sim import Fault, FaultKind, FaultSchedule, SimulationEngine, get_scenario
from simurg.sim.actuators import ActuatorState
from simurg.sim.health import HealthSupervisor


class NanProvider:
    source_id = "BOZUK"

    def provide(self, t):
        return SensorMeasurement("BOZUK", t, np.array([np.nan, 0.0]), np.eye(2), valid=True)


class GoodProvider:
    def __init__(self, sid):
        self.source_id = sid

    def provide(self, t):
        return SensorMeasurement(self.source_id, t, np.array([1.0, 2.0]), np.eye(2) * 4.0)


class UnknownIsNotHealthyTest(unittest.TestCase):
    def test_unobserved_motors_are_not_counted_for_hover_when_airborne(self):
        v = VehicleConfig()
        hs = HealthSupervisor(v.actuator_ids, 8, v.rpm_max, v.weight_n)
        idle = ActuatorState(np.zeros(12), np.zeros(12), np.zeros(12), np.ones(12), (), 0.0)
        hs.update(idle, np.zeros(8), 1.0, 0.0, airborne=False)
        self.assertGreater(hs.hover_margin, 1.5)        # yerde: ESC öz-testi varsayımı
        hs.update(idle, np.zeros(8), 1.0, 0.1, airborne=True)
        self.assertLess(hs.hover_margin, 1e-3)          # havada: gözlenmemiş = çalışmıyor
        self.assertTrue(hs.unknown_mask[:8].all())

    def test_navigation_without_solution_never_reports_integrity(self):
        eng = SimulationEngine(get_scenario("nominal"))
        self.assertFalse(eng.nav_sol.integrity_ok)
        self.assertFalse(math.isfinite(eng.nav_sol.protection_level_m))
        sol = NavigationSystem([]).update(0.0, 10.0, np.zeros(3))
        self.assertFalse(sol.integrity_ok)
        self.assertEqual(sol.confidence, 0.0)

    def test_nonfinite_measurement_is_treated_as_unavailable(self):
        sol = NavigationSystem([NanProvider(), GoodProvider("A"), GoodProvider("B")]).update(
            0.0, 10.0, np.zeros(3))
        self.assertEqual(sol.sources_unavailable, ("BOZUK",))
        self.assertEqual(sol.sources_used, ("A", "B"))
        self.assertTrue(np.all(np.isfinite(sol.position_ned)))

    def test_unknown_energy_estimate_raises_warning(self):
        a = ReserveMonitor(1.6).assess(float("nan"), 500.0, 24.0, 590.0)
        self.assertTrue(a.warn_now and a.warning_active)
        self.assertEqual(a.to_dict()["reason"], "enerji_kestirimi_yok")


class ExplicitDegradationTest(unittest.TestCase):
    def test_airspeed_loss_uses_explicit_fallback_and_is_reported(self):
        sc = replace(get_scenario("nominal"), name="pitot_loss", faults=FaultSchedule((
            Fault("P", FaultKind.SENSOR_DROPOUT, "sensor:AIRSPEED", 40.0, 20.0),)))
        r = SimulationEngine(sc).run()
        deg = [e for e in r.events if e["type"] == EventType.SENSOR_DEGRADED.value]
        res = [e for e in r.events if e["type"] == EventType.SENSOR_RESTORED.value]
        self.assertEqual(len(deg), 1)
        self.assertEqual(deg[0]["data"]["fallback"], "yer_hizi_kestirimi")
        self.assertAlmostEqual(deg[0]["time_s"], 40.0, delta=0.05)
        self.assertAlmostEqual(res[0]["time_s"], 60.0, delta=0.05)
        snap = next(s for s in r.log["snapshots"] if 45 < s["t"] < 55)
        self.assertEqual(snap["airdata_degraded"], ["AIRSPEED"])
        self.assertTrue(r.passed, r.expectation_failures)

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises(ConfigurationError):
            VehicleConfig(mass_kg=-1.0)
        with self.assertRaises(ConfigurationError):
            SimulationConfig(dt_s=0.0)
        with self.assertRaises(ConfigurationError):
            SimulationEngine(replace(get_scenario("nominal"), sim=SimulationConfig(integrator="yok")))

    def test_state_corruption_is_a_simulation_error_not_silent(self):
        class Corrupt(AnalyticAeroModel):
            calls = 0

            def evaluate(self, inp):
                Corrupt.calls += 1
                out = super().evaluate(inp)
                if Corrupt.calls > 3000:
                    return replace(out, force_body=out.force_body * np.nan)
                return out

        eng = SimulationEngine(replace(get_scenario("nominal"), aero_factory=Corrupt))
        with self.assertRaises(SimulationError):
            eng.run()
        types = [e["type"] for e in eng.recorder.events]
        self.assertEqual(types[-1], EventType.SIM_FAILED.value)
        self.assertTrue(eng.finished)


if __name__ == "__main__":
    unittest.main()
