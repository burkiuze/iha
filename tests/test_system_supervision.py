"""Komut doğrulayıcı, uçuş öncesi denetçi, araç sağlık modeli ve sistem denetçisi."""

import dataclasses
import math
import unittest
from dataclasses import replace

import numpy as np

from simurg.core.config import SafetyConfig, VehicleConfig
from simurg.core.events import EventType
from simurg.core.types import HealthState, NavigationSolution
from simurg.fdir.lanes import LaneState
from simurg.fdir.vehicle_health import Domain, VehicleHealthLevel, VehicleHealthModel, worst
from simurg.modes.flight_modes import Mode
from simurg.safety.command_validator import CommandValidator
from simurg.safety.rta import Command, Envelope
from simurg.sim import (Fault, FaultKind, FaultSchedule, InitialConditions, MissionProfile,
                        SimulationEngine, get_scenario)
from simurg.sim.preflight import CHECK_NAMES, PreflightInputs, PreflightSupervisor
from simurg.sim.supervisor import SystemState, SystemSupervisor

try:
    from ._simcache import scenario_result
except ImportError:
    from _simcache import scenario_result


def nav(ok=True, rejected=(), unavailable=()):
    return NavigationSolution(np.zeros(3), np.zeros(3), 0.9, 10.0, ("A", "B"), rejected,
                              unavailable, ok, 0.0)


def health(**kw):
    args = dict(actuator_states={"M1U": HealthState.NOMINAL}, hover_feasible=True, airborne=True,
                degraded_sensors=[], nav=nav(), nav_initialized=True, energy_health=1.0,
                usable_energy_wh=500.0, energy_warning=False, unmet_power_w=0.0, link_up=True,
                controllable=True, lane_states={l: LaneState.NOMINAL for l in "ABC"},
                proposal_ok=True)
    args.update(kw)
    return VehicleHealthModel().assess(**args)


class CommandValidatorTest(unittest.TestCase):
    def test_accepts_plausible_and_rejects_invalid_without_clipping(self):
        v = CommandValidator()
        ok = v.validate(Command(30.0, 5.0, 24.0))
        self.assertTrue(ok.accepted)
        self.assertEqual(ok.command, Command(30.0, 5.0, 24.0))
        self.assertEqual(v.validate(Command(math.nan, 0, 24)).reasons, ("sonlu_degil",))
        self.assertEqual(v.validate("sola dön").reasons, ("tip_gecersiz",))
        r = v.validate(Command(120.0, 70.0, 99.0))
        self.assertFalse(r.accepted)
        self.assertIsNone(r.command)                 # kırpılmış komut üretilmez
        self.assertEqual(set(r.reasons), {"yatis_fiziksel_sinir_disi",
                                          "yunuslama_fiziksel_sinir_disi", "hiz_fiziksel_sinir_disi"})

    def test_invalid_ai_proposal_never_reaches_rta_in_simulation(self):
        sc = replace(get_scenario("nominal"), name="nan_proposal", duration_s=90.0,
                     faults=FaultSchedule((Fault("AI", FaultKind.CONTROLLER_FAULT, "controller:advanced",
                                                 40.0, 10.0, params={"bank_deg": float("nan")}),)))
        r = SimulationEngine(sc).run()
        rej = [e for e in r.events if e["type"] == EventType.COMMAND_REJECTED.value]
        acc = [e for e in r.events if e["type"] == EventType.COMMAND_ACCEPTED.value]
        self.assertEqual(len(rej), 1)
        self.assertEqual(rej[0]["data"]["reasons"], ["sonlu_degil"])
        self.assertAlmostEqual(rej[0]["time_s"], 40.0, delta=0.05)
        self.assertAlmostEqual(acc[0]["time_s"], 50.0, delta=0.05)
        self.assertEqual(r.metrics.rta_interventions, 0)     # RTA'ya NaN hiç ulaşmadı
        self.assertFalse(r.metrics.rta_latched)
        self.assertFalse(r.metrics.impact)
        self.assertEqual(r.metrics.commands_rejected, 1)


class PreflightTest(unittest.TestCase):
    def inputs(self, **kw):
        base = dict(sensor_status={s: True for s in ("BARO", "AIRSPEED", "RPM", "GNSS", "VIO")},
                    nav_sources=("GNSS", "VIO", "TRN"), min_nav_sources=2, usable_energy_wh=500.0,
                    mission_distance_m=2000.0, cruise_speed_mps=24.0, cruise_power_w=590.0,
                    hover_margin=1.6, failed_actuators=(), link_up=True,
                    waypoints=((500.0, 0.0),), home_ne=(0.0, 0.0), takeoff_alt_m=50.0,
                    safety=SafetyConfig(), soft=Envelope(),
                    hard=Envelope(15, 15, 42, 65, 35, 10),
                    lane_heartbeat={"A": True, "B": True, "C": True}, rta_latched=False,
                    recorder_ok=True)
        base.update(kw)
        return PreflightInputs(**base)

    def test_all_eleven_checks_and_pass(self):
        rep = PreflightSupervisor().run(self.inputs())
        self.assertEqual(tuple(c.name for c in rep.checks), CHECK_NAMES)
        self.assertEqual(len(CHECK_NAMES), 11)
        self.assertTrue(rep.passed)

    def test_each_failure_blocks_arming(self):
        cases = {
            "sensor_health": dict(sensor_status={"BARO": True, "AIRSPEED": False, "RPM": True,
                                                 "GNSS": True, "VIO": True}),
            "navigation": dict(sensor_status={"BARO": True, "AIRSPEED": True, "RPM": True, "GNSS": True}),
            "energy": dict(usable_energy_wh=50.0),
            "fcc_lanes": dict(lane_heartbeat={"A": True, "B": False, "C": True}),
            "rta": dict(safety=SafetyConfig(hover_margin_min=0.8)),
            "control_authority": dict(hover_margin=1.05),
            "actuator_health": dict(failed_actuators=("M1U",)),
            "communication": dict(link_up=False),
            "mission_validation": dict(waypoints=((9000.0, 0.0),)),
            "recorder": dict(recorder_ok=False),
        }
        for name, kw in cases.items():
            with self.subTest(name):
                rep = PreflightSupervisor().run(self.inputs(**kw))
                self.assertFalse(rep.passed)
                self.assertEqual(rep.failed, (name,))

    def test_unknown_energy_does_not_pass(self):
        rep = PreflightSupervisor().run(self.inputs(usable_energy_wh=float("nan")))
        self.assertEqual(rep.failed, ("energy",))

    def test_unknown_lane_rta_and_recorder_state_do_not_pass(self):
        rep = PreflightSupervisor().run(self.inputs(lane_heartbeat=None, rta_latched=None,
                                                    recorder_ok=None))
        self.assertEqual(rep.failed, ("fcc_lanes", "rta", "recorder"))
        self.assertFalse(rep.passed)

    def test_latched_rta_blocks_arming(self):
        rep = PreflightSupervisor().run(self.inputs(rta_latched=True))
        self.assertEqual(rep.failed, ("rta",))

    def test_failed_preflight_never_arms_or_takes_off(self):
        for label, sc in (
            ("energy", replace(get_scenario("nominal"), initial=InitialConditions(0.25, 0.0))),
            ("communication", replace(get_scenario("nominal"), faults=FaultSchedule((
                Fault("L", FaultKind.LINK_LOSS, "link:c2", 0.0),)))),
            ("actuator_health", replace(get_scenario("nominal"), faults=FaultSchedule((
                Fault("M", FaultKind.ACTUATOR_OFFLINE, "actuator:M3L", 0.0),)))),
            ("fcc_lanes", replace(get_scenario("nominal"), faults=FaultSchedule((
                Fault("L", FaultKind.FCC_LANE_UNAVAILABLE, "fcc:C", 0.0),)))),
        ):
            with self.subTest(label):
                r = SimulationEngine(sc).run()
                ev = [e for e in r.events if e["type"] == EventType.PREFLIGHT_FAILED.value]
                self.assertEqual(ev[0]["data"]["failed_checks"], [label])
                self.assertEqual(r.final_state.flight_mode, "PREFLIGHT")
                self.assertTrue(r.final_state.landed)
                self.assertEqual(r.metrics.mission_outcome_reason, f"preflight_basarisiz:{label}")
                self.assertFalse(any(e["type"] == "mode_transition" for e in r.events))

    def test_library_scenarios_pass_preflight(self):
        r = scenario_result("nominal")
        ev = next(e for e in r.events if e["type"] == EventType.PREFLIGHT_PASSED.value)
        self.assertEqual([c["name"] for c in ev["data"]["checks"]], list(CHECK_NAMES))


class VehicleHealthModelTest(unittest.TestCase):
    def test_nominal(self):
        self.assertIs(health().overall, HealthState.NOMINAL)

    def test_unknown_is_never_nominal(self):
        self.assertIs(health(nav=None).domain(Domain.NAVIGATION).state, HealthState.UNKNOWN)
        self.assertIs(health(nav_initialized=False).overall, HealthState.UNKNOWN)
        self.assertIs(health(usable_energy_wh=float("nan")).domain(Domain.POWER).state,
                      HealthState.UNKNOWN)
        self.assertIs(health(actuator_states={"M1U": HealthState.UNKNOWN}).overall,
                      HealthState.UNKNOWN)
        self.assertIs(health(lane_states=None).domain(Domain.FCC).state, HealthState.UNKNOWN)
        self.assertIs(health(proposal_ok=None).domain(Domain.MISSION_COMPUTER).state,
                      HealthState.UNKNOWN)
        self.assertIs(health(nav=None).level, VehicleHealthLevel.UNKNOWN)
        self.assertIsNot(health(lane_states=None).level, VehicleHealthLevel.NOMINAL)
        self.assertIs(worst([]), HealthState.UNKNOWN)
        self.assertIs(worst([HealthState.DEGRADED, HealthState.UNKNOWN]), HealthState.UNKNOWN)

    def test_redundancy_and_domains(self):
        tolerated = health(actuator_states={"M1U": HealthState.FAILED}, hover_feasible=True)
        self.assertIs(tolerated.domain(Domain.MOTORS).state, HealthState.DEGRADED)
        self.assertIs(tolerated.level, VehicleHealthLevel.DEGRADED)
        lost = health(actuator_states={"M1U": HealthState.FAILED}, hover_feasible=False)
        self.assertIs(lost.domain(Domain.MOTORS).state, HealthState.FAILED)
        self.assertIs(lost.domain(Domain.CONTROL).state, HealthState.DEGRADED)
        self.assertIs(lost.level, VehicleHealthLevel.CRITICAL)
        surf = health(actuator_states={"M1U": HealthState.NOMINAL, "E1U": HealthState.FAILED,
                                       "E2U": HealthState.NOMINAL})
        self.assertIs(surf.domain(Domain.ACTUATORS).state, HealthState.DEGRADED)
        all_surf = health(actuator_states={"E1U": HealthState.FAILED, "E2U": HealthState.FAILED})
        self.assertIs(all_surf.domain(Domain.ACTUATORS).state, HealthState.FAILED)
        self.assertIs(health(nav=nav(ok=False)).domain(Domain.NAVIGATION).state, HealthState.FAILED)
        self.assertIs(health(nav=nav(rejected=("GNSS",))).domain(Domain.NAVIGATION).state,
                      HealthState.DEGRADED)
        self.assertIs(health(link_up=False).domain(Domain.COMMUNICATION).state, HealthState.FAILED)
        self.assertIs(health(unmet_power_w=100.0).domain(Domain.POWER).state, HealthState.FAILED)
        self.assertIs(health(unmet_power_w=100.0).level, VehicleHealthLevel.CONTINGENCY)
        one = health(lane_states={"A": LaneState.FAILED, "B": LaneState.ISOLATED,
                                  "C": LaneState.NOMINAL})
        self.assertIs(one.domain(Domain.FCC).state, HealthState.FAILED)
        self.assertIs(one.level, VehicleHealthLevel.CONTINGENCY)
        none = health(lane_states={l: LaneState.FAILED for l in "ABC"})
        self.assertIs(none.level, VehicleHealthLevel.CRITICAL)
        two = health(lane_states={"A": LaneState.ISOLATED, "B": LaneState.NOMINAL,
                                  "C": LaneState.NOMINAL})
        self.assertIs(two.domain(Domain.FCC).state, HealthState.DEGRADED)
        mc = health(proposal_ok=False, proposal_rejected_s=5.0)
        self.assertIs(mc.domain(Domain.MISSION_COMPUTER).state, HealthState.FAILED)

    def test_every_domain_has_standard_fdir_report(self):
        vh = health()
        self.assertEqual({r.domain.value for r in vh.reports},
                         {"sensor", "navigation", "fcc", "motor", "actuator", "energy",
                          "communication", "mission_computer"})
        for r in vh.reports:
            d = r.to_dict()
            for k in ("fault_detected", "fault_isolated", "fault_class", "confidence",
                      "health_state", "recommended_degradation"):
                self.assertIn(k, d)
        bad = health(link_up=False).to_dict()["fdir_reports"]
        comm = next(r for r in bad if r["domain"] == "communication")
        self.assertTrue(comm["fault_detected"])
        self.assertEqual(comm["fault_class"], "link_loss")


class SystemSupervisorTest(unittest.TestCase):
    def assess(self, **kw):
        a = dict(mode=Mode.MISSION, health=health(), rta_on_safety=False, rta_latched=False,
                 contingency_mode=False, energy_warning=False, proposal_rejected=False)
        a.update(kw)
        return SystemSupervisor().assess(**a)

    def test_state_rules(self):
        self.assertIs(self.assess().state, SystemState.NORMAL)
        self.assertIs(self.assess(rta_on_safety=True).state, SystemState.DEGRADED)
        self.assertIs(self.assess(health=health(nav=None)).state, SystemState.DEGRADED)  # unknown
        self.assertIs(self.assess(rta_latched=True).state, SystemState.CONTINGENCY)
        self.assertIs(self.assess(health=health(link_up=False)).state, SystemState.CONTINGENCY)
        self.assertIs(self.assess(mode=Mode.PARACHUTE).state, SystemState.EMERGENCY)
        self.assertIs(self.assess(health=health(controllable=False)).state, SystemState.EMERGENCY)
        self.assertIs(self.assess(health=health(
            lane_states={l: LaneState.FAILED for l in "ABC"})).state, SystemState.EMERGENCY)
        self.assertIs(self.assess(health=health(unmet_power_w=50.0)).state, SystemState.CONTINGENCY)

    def test_supervisor_in_library_scenarios(self):
        expect = {"nominal": "normal", "single_actuator_degradation": "degraded",
                  "rta_intervention": "degraded", "communication_loss": "contingency",
                  "nav_integrity_loss": "contingency", "hover_capability_loss": "emergency",
                  "loss_of_control": "emergency", "fcc_lane_divergence": "degraded",
                  "fcc_lane_loss": "degraded", "mission_computer_failure": "contingency"}
        for name, worst_state in expect.items():
            with self.subTest(name):
                r = scenario_result(name)
                self.assertEqual(r.metrics.worst_system_state, worst_state)
                changes = [e for e in r.events if e["type"] == EventType.SYSTEM_STATE_CHANGED.value]
                self.assertEqual(changes[0]["data"]["state"], "normal")
                self.assertTrue(all(e["data"]["reason"] for e in changes))


class ConfigurationImmutabilityTest(unittest.TestCase):
    def test_safety_critical_configuration_is_frozen(self):
        for obj, field in ((SafetyConfig(), "hover_margin_min"), (VehicleConfig(), "mass_kg"),
                           (MissionProfile(), "cruise_alt_m"), (get_scenario("nominal"), "seed")):
            with self.assertRaises(dataclasses.FrozenInstanceError):
                setattr(obj, field, 0)


if __name__ == "__main__":
    unittest.main()
