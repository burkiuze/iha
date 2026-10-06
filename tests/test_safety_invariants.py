"""Mimari güvenlik değişmezleri (docs/08 §6, docs/14 §13).

Her test bir değişmezi adıyla belgeler; değişmez bozulursa test başarısız olur.
"""

import ast
import math
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

from simurg.config import WEIGHT_N, hover_effectiveness
from simurg.control.allocation import ControlAllocator
from simurg.core.errors import InvalidScenarioError, SafetyInvariantError
from simurg.core.events import EventType
from simurg.modes.flight_modes import (AIRBORNE_MODES, TRANSITIONS, Context, FlightModeMachine,
                                       Mode)
from simurg.safety.rta import (Command, EnvelopeState, RuntimeAssurance, Source,
                               ValidatedCommand)
from simurg.sim import (Fault, FaultKind, FaultSchedule, ReplaySession, Scenario,
                        SimulationEngine, get_scenario)
from simurg.sim.scenarios import SCENARIOS

try:
    from ._simcache import scenario_result
except ImportError:
    from _simcache import scenario_result

ROOT = Path(__file__).resolve().parent.parent
SAFE = Command(0.0, 3.0, 24.0)


def state(**kw):
    s = dict(alt_agl_m=150, airspeed_mps=25, bank_deg=0, pitch_deg=3, climb_mps=0,
             fence_dist_m=2000, fence_closing_mps=0)
    s.update(kw)
    return EnvelopeState(**s)


def imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            out.add(("." * n.level) + (n.module or ""))
        elif isinstance(n, ast.Import):
            out.update(a.name for a in n.names)
    return out


class RtaInvariantTest(unittest.TestCase):
    def test_rta_latched_never_selects_advanced(self):
        rng = np.random.default_rng(3)
        rta = RuntimeAssurance(recovery_cycles=1)
        rta.decide(state(alt_agl_m=5.0), Command(0, 3, 24), SAFE)
        self.assertTrue(rta.latched)
        for _ in range(2000):
            s = state(alt_agl_m=float(rng.uniform(50, 500)), bank_deg=float(rng.uniform(-30, 30)))
            ac = Command(float(rng.uniform(-20, 20)), float(rng.uniform(-5, 10)), 24.0)
            d = rta.decide(s, ac, SAFE)
            self.assertIs(d.selected_source, Source.SAFETY)
            self.assertIs(d.command, SAFE)

    def test_hard_envelope_violation_denies_advanced_authority(self):
        for kw in ({"alt_agl_m": 10.0}, {"bank_deg": 70.0}, {"airspeed_mps": 50.0},
                   {"fence_dist_m": 5.0}, {"pitch_deg": -40.0}):
            d = RuntimeAssurance().decide(state(**kw), Command(0, 3, 24), SAFE)
            self.assertIs(d.selected_source, Source.SAFETY, kw)
            self.assertTrue(d.latched, kw)
            self.assertTrue(d.current_violations, kw)

    def test_nonfinite_state_is_not_treated_as_safe(self):
        d = RuntimeAssurance().decide(state(airspeed_mps=math.nan), Command(0, 3, 24), SAFE)
        self.assertIs(d.selected_source, Source.SAFETY)
        self.assertIn("gecersiz_durum", d.current_violations)
        self.assertTrue(d.latched)


class AiAuthorityBoundaryTest(unittest.TestCase):
    def test_validated_command_cannot_be_forged(self):
        with self.assertRaises(SafetyInvariantError):
            ValidatedCommand(Command(80, 0, 24), Source.ADVANCED, 0.0)

    def test_rta_output_is_the_only_validated_command_source(self):
        d = RuntimeAssurance().decide(state(), Command(10, 3, 24), SAFE, 1.0)
        self.assertIsInstance(d.validated, ValidatedCommand)
        self.assertIs(d.validated.command, d.command)
        v = RuntimeAssurance().safety_only(SAFE, 2.0, "acil")
        self.assertIs(v.source, Source.SAFETY)

    def test_controller_rejects_unvalidated_command(self):
        eng = SimulationEngine(replace(get_scenario("nominal"), duration_s=30.0))
        eng.run()                                    # araç havada, CRUISE/MISSION
        self.assertIn(eng.mode, (Mode.CRUISE, Mode.MISSION))
        import simurg.core.frames as fr
        R = fr.quat_to_dcm(eng.x[6:10])
        ci = eng._control_inputs(R, R.T @ eng.x[3:6], None)
        with self.assertRaises(SafetyInvariantError):          # komutsuz sabit kanat yasası yok
            eng.controller.compute(ci, eng.plan, 24.0)
        raw = replace(ci, command=Command(85.0, 40.0, 30.0))
        with self.assertRaises(SafetyInvariantError):          # ham AC önerisi reddedilir
            eng.controller.compute(raw, eng.plan, 24.0)

    def test_ai_layer_has_no_import_path_to_actuation(self):
        forbidden = ("allocation", "effectiveness", "flight_controller", "vehicle_control",
                     "actuators", "propulsion", "sim")
        for rel in ("simurg/control/guidance.py", "simurg/swarm/auction.py"):
            for imp in imports_of(ROOT / rel):
                self.assertFalse(any(f in imp.split(".") for f in forbidden), f"{rel}: {imp}")
        for imp in imports_of(ROOT / "simurg/sim/vehicle_control.py"):
            self.assertNotIn("guidance", imp)

    def test_ai_cannot_drive_vehicle_outside_hard_envelope(self):
        sc = replace(get_scenario("nominal"), name="ai_misbehaves", duration_s=110.0,
                     faults=FaultSchedule((Fault("AI", FaultKind.CONTROLLER_FAULT,
                                                 "controller:advanced", 30.0,
                                                 params={"bank_deg": 85.0}),)))
        r = SimulationEngine(sc).run()
        self.assertGreater(r.metrics.rta_interventions, 0)
        self.assertFalse(r.metrics.impact)
        fw = [s for s in r.log["snapshots"] if s["mode"] in ("CRUISE", "MISSION", "RETURN", "LOITER_HOLD")
              and s["t"] > 30.0]
        self.assertTrue(fw)
        self.assertLess(max(abs(s["att_deg"][2]) for s in fw), RuntimeAssurance().hard.max_bank_deg)


class ModeInvariantTest(unittest.TestCase):
    def test_parachute_mode_is_terminal_in_air(self):
        self.assertEqual(FlightModeMachine.allowed_targets(Mode.PARACHUTE), [Mode.DISARMED])
        fsm = FlightModeMachine()
        fsm.mode = Mode.PARACHUTE
        airborne = Context(landed=False, nav_integrity_ok=True, airspeed_mps=25.0)
        for m in Mode:
            if m is not Mode.PARACHUTE:
                self.assertFalse(fsm.request(m, airborne))
        self.assertIs(fsm.mode, Mode.PARACHUTE)

    def test_airborne_vehicle_cannot_disarm(self):
        sources = [s for (s, t) in TRANSITIONS if t is Mode.DISARMED]
        for s in sources:
            self.assertFalse(TRANSITIONS[(s, Mode.DISARMED)](Context(landed=False)), s)
        for m in AIRBORNE_MODES:
            fsm = FlightModeMachine()
            fsm.mode = m
            self.assertFalse(fsm.request(Mode.DISARMED, Context(landed=False)), m)

    def test_mode_changes_only_through_transition_table(self):
        for name in SCENARIOS:
            for e in scenario_result(name).events:
                if e["type"] == EventType.MODE_TRANSITION.value:
                    key = (Mode[e["data"]["source"]], Mode[e["data"]["target"]])
                    self.assertIn(key, TRANSITIONS, (name, key))


class FdirInvariantTest(unittest.TestCase):
    def test_failed_actuator_not_treated_as_nominal(self):
        alloc = ControlAllocator(*hover_effectiveness())
        h = np.ones(12)
        h[3] = 0.0
        r = alloc.allocate([WEIGHT_N, 1.0, -1.0, 0.5], h)
        self.assertEqual(r.u[3], 0.0)
        np.testing.assert_allclose(r.achieved, (alloc.B * h) @ r.u)
        # simülasyonda: kalıcı devre dışı motorun sağlığı 0 ve dağıtıcı ona komut vermez
        sc = replace(get_scenario("hover_capability_loss"), duration_s=60.0)
        eng = SimulationEngine(sc)
        eng.run()
        idx = sc.vehicle.actuator_ids.index("M1U")
        self.assertEqual(eng.health.health[idx], 0.0)
        self.assertEqual(eng.controller.last_allocation.u[idx], 0.0)


class SimulationInvariantTest(unittest.TestCase):
    def test_simulation_is_deterministic_for_same_seed(self):
        sc = replace(get_scenario("combined_degraded", 11), duration_s=40.0)
        a, b = SimulationEngine(sc).run(), SimulationEngine(sc).run()
        self.assertEqual(a.log, b.log)

    def test_invalid_scenario_is_never_run_silently(self):
        with self.assertRaises(InvalidScenarioError):
            SimulationEngine(Scenario("bad", duration_s=0.0)).run()

    def test_fault_schedule_applied_deterministically(self):
        def act():
            eng = SimulationEngine(replace(get_scenario("combined_degraded", 5), duration_s=90.0))
            eng.run()
            return eng.injector.activation_times
        self.assertEqual(act(), act())

    def test_event_timestamps_and_simulation_time_never_go_backwards(self):
        for name in SCENARIOS:
            log = scenario_result(name).log
            seqs = [e["seq"] for e in log["events"]]
            times = [e["time_s"] for e in log["events"]]
            snaps = [s["t"] for s in log["snapshots"]]
            self.assertEqual(seqs, list(range(len(seqs))), name)
            self.assertTrue(all(b >= a for a, b in zip(times, times[1:])), name)
            self.assertTrue(all(b > a for a, b in zip(snaps, snaps[1:])), name)

    def test_replay_does_not_reorder_events(self):
        r = scenario_result("combined_degraded")
        s = ReplaySession.from_source(r)
        self.assertEqual([e["seq"] for e in s.events], [e["seq"] for e in r.events])
        self.assertTrue(s.ordering_is_consistent())


if __name__ == "__main__":
    unittest.main()
