"""Merkezi simülasyon motoru (dijital ikiz çekirdeği).

Her adım (tick) aşağıdaki SABİT sırayla çalışır (`TICK_ORDER`):

   1. scenario_events   arıza takvimi (FaultInjector)
   2. environment       rüzgâr, yoğunluk
   3. sensors           hava hızı, barometre (hızlı sensörler)
   4. navigation        konum kaynakları + bütünlük (nav periyodunda)
   5. health            FDIR: motor devir artığı, yüzey konum artığı
   6. proposals         görev yöneticisi (nominal mod ilerleyişi) + AC/SC önerileri
   7. rta               Simplex karar (yalnızca sabit kanat modlarında)
   8. allocation        iç döngü kontrol + rejime bağlı kontrol dağıtımı
   9. actuators         gecikme, tepki, doyma, eyleyici arızaları
  10. dynamics          6-DOF integrasyon + yer teması; zaman burada ilerler
  11. power             elektrik yükü -> enerji yöneticisi
  12. contingency       bağlantı, enerji, acil durum kuralları
  13. logging           anlık görüntü kaydı
  14. metrics           metrik biriktirme

Determinizm: tüm rastgelelik `numpy.random.SeedSequence(seed)`'ten türetilen
alt üreteçlerden gelir; küresel rastgele durum kullanılmaz.

Bilinen basitleştirmeler (bkz. docs/14-simulasyon-ve-dijital-ikiz.md):
  * tutum ve açısal hızlar kusursuz kestirici varsayımıyla gerçek değerden
    alınır; hava hızı ve irtifa gürültülü sensörden, yatay konum
    navigasyon çözümünden gelir.
  * gömülü aero kestirimi gerçek modelle aynıdır (model uyumsuzluğu yok).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..aero.model import AeroInputs, AnalyticAeroModel
from ..control.allocation import ControlAllocator, ScheduledAllocator
from ..control.effectiveness import (EffectivenessConditions, HoverEffectiveness,
                                     ScheduledEffectiveness, body_to_alloc)
from ..control.flight_controller import AttitudeSetpoint, FlightController
from ..control.guidance import MissionGuidance, SafetyController
from ..control.transition import TransitionCoordinator, TransitionPhase, TransitionStatus
from ..core.events import EventBus, EventType
from ..core.frames import attitude_angles, quat_from_euler, quat_to_dcm
from ..core.types import HealthState, NavigationSolution, VehicleState
from ..fdir.monitor import MotorHealthMonitor, SurfaceMonitor
from ..modes.flight_modes import (FIXED_WING_MODES, Context, ContingencyManager,
                                  FlightModeMachine, Mode, TransitionRecord)
from ..nav.integrity import IntegrityMonitor
from ..nav.providers import NavigationSystem
from ..power.energy_manager import EnergyManager
from ..safety.rta import Command, EnvelopeState, RuntimeAssurance, Source
from .actuators import ActuatorCommand, ActuatorModel, ActuatorState, rpm_from_output
from .dynamics import MassProperties, RigidBodyDynamics, Wrench, integrate, make_integrator
from .environment import ConstantEnvironment, EnvironmentState, ScriptedEnvironment
from .faults import ControllerFaultTarget, EnergyFaultTarget, FaultInjector
from .link import LinkModel
from .metrics import MetricsAccumulator, SimulationMetrics, compute_metrics
from .propulsion import PropulsionModel
from .recorder import SimulationRecorder
from .scenario import Scenario
from .sensors import DEFAULT_POSITION_SOURCES, SensorModel, SensorSuite, SimulatedPositionProvider

log = logging.getLogger(__name__)

TICK_ORDER: tuple[str, ...] = (
    "scenario_events", "environment", "sensors", "navigation", "health", "proposals",
    "rta", "allocation", "actuators", "dynamics", "power", "contingency", "logging",
    "metrics",
)

LANDING_ENERGY_WH = 60.0
_HOVER_MODES = {Mode.VTOL_TAKEOFF, Mode.VTOL_LAND}
_IDLE_MODES = {Mode.PREFLIGHT, Mode.ARMED, Mode.DISARMED, Mode.PARACHUTE}
_RESERVE_LOCKED = {Mode.CRUISE, Mode.MISSION, Mode.LOITER_HOLD}


@dataclass
class SimulationResult:
    scenario: str
    seed: int
    final_state: VehicleState
    metrics: SimulationMetrics
    log: dict[str, Any]
    expectation_failures: list[str]

    @property
    def passed(self) -> bool:
        return not self.expectation_failures

    @property
    def events(self) -> list[dict[str, Any]]:
        return self.log["events"]


class SimulationEngine:
    def __init__(self, scenario: Scenario) -> None:
        scenario.validate()
        self.sc = scenario
        cfg, v, m = scenario.sim, scenario.vehicle, scenario.mission
        self.dt = cfg.dt_s
        self.nav_every = max(1, int(round(cfg.nav_period_s / cfg.dt_s)))
        self.vehicle = v
        rngs = [np.random.default_rng(s) for s in np.random.SeedSequence(scenario.seed).spawn(9)]

        self.bus = EventBus()
        self.aero = scenario.aero_factory() if scenario.aero_factory else AnalyticAeroModel()
        meta = {**scenario.describe(), "aero_provenance": self.aero.coefficients.provenance,
                "tick_order": list(TICK_ORDER), "actuator_ids": list(v.actuator_ids)}
        self.recorder = SimulationRecorder(self.bus, cfg.snapshot_period_s, meta)

        env_cfg = scenario.environment
        self.env = (ScriptedEnvironment(list(scenario.wind_keyframes), env_cfg)
                    if scenario.wind_keyframes else ConstantEnvironment(env_cfg))
        self.env.bind_rng(rngs[0])

        self.dyn = RigidBodyDynamics(MassProperties.from_vehicle(v))
        self.integ = make_integrator(cfg.integrator)
        self.prop = PropulsionModel(v)
        n_m, n_s = len(v.motors), len(v.surfaces)
        self.n_m = n_m
        tau = np.array([v.motor_tau_s] * n_m + [v.surface_tau_s] * n_s)
        self.act = ActuatorModel(v.actuator_ids, np.array([0.0] * n_m + [-1.0] * n_s),
                                 np.ones(n_m + n_s), tau, v.actuator_latency_s, self.dt)
        self._sy = np.array([s.y for s in v.surfaces])

        pos_sensors = [SensorModel(sid, [sig, sig], rngs[1 + i])
                       for i, (sid, sig) in enumerate(DEFAULT_POSITION_SOURCES.items())]
        self.baro = SensorModel("BARO", 0.3, rngs[5])
        self.pitot = SensorModel("AIRSPEED", 0.3, rngs[6])
        self.rpm_sensor = SensorModel("RPM", np.full(n_m, 15.0), rngs[7])
        self.sensors = SensorSuite(pos_sensors + [self.baro, self.pitot, self.rpm_sensor])
        self.nav = NavigationSystem([SimulatedPositionProvider(s, self._truth_ne)
                                     for s in pos_sensors], IntegrityMonitor())

        self.mhm = MotorHealthMonitor(n=n_m, min_observable_abs=0.25 * v.rpm_max)
        self.smon = SurfaceMonitor(n=n_s)
        self.health_est = np.ones(n_m + n_s)

        self.em = EnergyManager()
        self.em.batt_soc = scenario.initial.battery_soc
        self.em.h2_wh *= scenario.initial.hydrogen_fraction
        self.link = LinkModel()

        self.fsm = FlightModeMachine(clock=lambda: self.t, listener=self._on_mode_record)
        self.cm = ContingencyManager()
        self.fc = FlightController(v)
        self.guid = MissionGuidance()
        self.safe = SafetyController(m.cruise_alt_m, m.cruise_speed_mps)
        sf = scenario.safety
        self.rta = RuntimeAssurance(horizon_s=sf.rta_horizon_s, recovery_cycles=sf.rta_recovery_cycles)
        self.trans = TransitionCoordinator()
        self.alloc = ScheduledAllocator(ScheduledEffectiveness(v))
        self._hover_alloc = ControlAllocator.from_regime(HoverEffectiveness().regime())

        self.injector = FaultInjector(scenario.faults, {
            "actuator": self.act, "sensor": self.sensors, "link": self.link,
            "energy": EnergyFaultTarget(self.em), "controller": ControllerFaultTarget(self.guid),
        }, self.bus)

        self.home = np.array(m.home_ne, float)
        self.hover_heading = math.radians(m.departure_heading_deg)
        q0 = quat_from_euler(self.hover_heading, math.pi / 2, 0.0)
        self.x = np.concatenate([[self.home[0], self.home[1], 0.0], np.zeros(3), q0, np.zeros(3)])
        self.t = 0.0
        self.tick = 0
        self.landed = True
        self.finished = False
        self.mission_complete = False
        self.wp_index = 0
        self.waypoints_done = False
        self.aborted = False
        self.hover_target = self.home.copy()
        self.alt_meas = 0.0
        self.airspeed = 0.0
        self.sat_frac = 0.0
        self.att_err = 0.0
        self.trans_status: TransitionStatus | None = None
        self._trans_alt = 0.0
        self._el_vertical = True
        self._chute_t: float | None = None
        self._loc_timer = 0.0
        self._loiter_since = 0.0
        self._power_factor = 1.0
        self._energy_warned = False
        self._link_up = True
        self._link_lost_s = 0.0
        self._rta_latched_pub = False
        self._fdir_seen: dict[str, HealthState] = {}
        self._fdir_sig: tuple | None = None
        self._rej_key: tuple | None = None
        self._margin_cache: dict[tuple, float] = {}
        self._hover_margin = self._hover_alloc.hover_margin(v.weight_n)
        self.nav_sol = NavigationSolution(np.array([*self.home, 0.0]), np.zeros(3), 1.0, 0.0,
                                          (), (), (), True, 0.0)
        self.ctx = Context(preflight_ok=True)
        self.acc = MetricsAccumulator()
        self._started = False

    # ================================================================== API
    def run(self) -> SimulationResult:
        self.start()
        while not self.finished and self.t < self.sc.duration_s - 1e-9:
            self.step()
        return self.finish()

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self.bus.publish(EventType.SIM_STARTED, 0.0, "engine", self.sc.name, seed=self.sc.seed)
        self.fsm.request(Mode.ARMED, self.ctx, "preflight_ok")
        self.fsm.request(Mode.VTOL_TAKEOFF, self.ctx, "gorev_baslat")
        self.recorder.maybe_snapshot(0.0, self._snapshot(), force=True)

    def step(self) -> None:
        dt = self.dt
        # 1. scenario events
        self.injector.update(self.t)
        # 2. environment
        envs = self.env.update(self.t, dt, self.x[0:3])
        self.envs = envs
        # 3. sensors
        R = quat_to_dcm(self.x[6:10])
        v_air_b = R.T @ (self.x[3:6] - envs.wind_ned)
        a = self.pitot.measure(float(np.linalg.norm(v_air_b)), self.t)
        if a.valid:
            self.airspeed = max(float(a.value[0]), 0.0)
        b = self.baro.measure(-self.x[2], self.t)
        if b.valid:
            self.alt_meas = float(b.value[0])
        # 4. navigation
        if self.tick % self.nav_every == 0:
            self._navigation()
        # 5. health
        self._health()
        # 6. proposals
        self._mission_manager()
        ac, sc = self._proposals()
        # 7. rta
        cmd = self._rta(ac, sc)
        # 8. allocation
        u = self._control(cmd, R, v_air_b)
        # 9. actuators
        st = self.act.step(ActuatorCommand(u, self.t))
        # 10. dynamics (zaman ilerler)
        self._dynamics(st, envs)
        self.t = round(self.t + dt, 9)
        self.tick += 1
        if self.finished:
            return
        # 11. power
        self._power(st, envs)
        # 12. contingency
        self._contingency()
        # 13. logging
        self.recorder.maybe_snapshot(self.t, self._snapshot())
        # 14. metrics
        self._metrics()
        if self.fsm.mode is Mode.DISARMED and self.sc.sim.stop_when_disarmed:
            self.finished = True

    def finish(self) -> SimulationResult:
        vs = self.vehicle_state()
        self.recorder.maybe_snapshot(self.t, self._snapshot(), force=True)
        self.bus.publish(EventType.SIM_FINISHED, self.t, "engine", self.fsm.mode.name)
        metrics = compute_metrics(
            self.recorder.events, self.acc, self.t, self.fsm.mode.name, self.mission_complete,
            [f.to_dict() for f in self.sc.faults], dict(self.injector.activation_times),
            self.em.usable_energy_wh(), self.em.reserve_energy_wh())
        self.recorder.finalize(metrics.to_dict())
        result = SimulationResult(self.sc.name, self.sc.seed, vs, metrics,
                                  self.recorder.to_dict(), [])
        result.expectation_failures = self.sc.expectations.evaluate(result)
        log.info("senaryo %s tohum %d bitti: mod=%s başarı=%s", self.sc.name, self.sc.seed,
                 metrics.final_mode, result.passed)
        return result

    # ============================================================ yardımcılar
    def _truth_ne(self) -> np.ndarray:
        return self.x[0:2].copy()

    @property
    def mode(self) -> Mode:
        return self.fsm.mode

    def _att(self) -> tuple[float, float, float]:
        return attitude_angles(quat_to_dcm(self.x[6:10]))

    def _pub(self, et: EventType, msg: str = "", /, **data: Any) -> None:
        self.bus.publish(et, self.t, "engine", msg, **data)

    def vehicle_state(self) -> VehicleState:
        vel = self.x[3:6]
        return VehicleState(self.t, self.x[0:3].copy(), vel.copy(), self.x[6:10].copy(),
                            self.x[10:13].copy(), self.airspeed,
                            float(np.hypot(vel[0], vel[1])), self.em.state(),
                            self.nav_sol.integrity_ok, self._link_up,
                            self.health_est.copy(), self.fsm.mode.name, self.landed)

    def _snapshot(self) -> dict[str, Any]:
        s = self.vehicle_state().snapshot()
        s.update({"rta": self.rta.source.value, "nav_pl": round(self.nav_sol.protection_level_m, 3)
                  if math.isfinite(self.nav_sol.protection_level_m) else None,
                  "sat": round(self.sat_frac, 4), "power_factor": round(self._power_factor, 4),
                  "transition": None if self.trans_status is None else self.trans_status.phase.value})
        return s

    def _fence(self) -> tuple[float, float]:
        rel = self.nav_sol.position_ned[:2] - self.home
        r = float(np.linalg.norm(rel))
        closing = float(np.dot(rel, self.x[3:5]) / r) if r > 1e-6 else 0.0
        return self.sc.safety.geofence_radius_m - r, closing

    def _dist_home(self) -> float:
        return float(np.linalg.norm(self.nav_sol.position_ned[:2] - self.home))

    # ================================================================ 4. nav
    def _navigation(self) -> None:
        prev = self.nav_sol
        sol = self.nav.update(self.t, self.alt_meas, self.x[3:6])
        self.nav_sol = sol
        for s in sorted(set(sol.sources_unavailable) - set(prev.sources_unavailable)):
            self._pub(EventType.NAV_SOURCE_UNAVAILABLE, s, source=s)
        for s in sorted(set(sol.sources_rejected) - set(prev.sources_rejected)):
            self._pub(EventType.NAV_SOURCE_REJECTED, s, source=s,
                      protection_level_m=sol.protection_level_m)
        if prev.integrity_ok and not sol.integrity_ok:
            self._pub(EventType.NAV_INTEGRITY_LOST, "", solution=sol.to_dict())
        elif not prev.integrity_ok and sol.integrity_ok:
            self._pub(EventType.NAV_INTEGRITY_RESTORED, "", solution=sol.to_dict())

    # ============================================================= 5. health
    def _health(self) -> None:
        st = self.act.last
        if st is None:
            return
        v = self.vehicle
        pf = self._power_factor
        rpm_exp = rpm_from_output(st.expected[:self.n_m] * pf, v.rpm_max)
        meas = self.rpm_sensor.measure(rpm_from_output(st.output[:self.n_m] * pf, v.rpm_max), self.t)
        if meas.valid:
            self.mhm.update(rpm_exp, meas.value)
        self.smon.update(st.expected[self.n_m:], st.position[self.n_m:])
        self.health_est = np.concatenate([self.mhm.health(), self.smon.health()])
        sig = (tuple(self.mhm.state), tuple(self.smon.failed))
        if sig == self._fdir_sig:
            reports = []
        else:
            self._fdir_sig = sig
            ids = v.actuator_ids
            reports = (self.mhm.reports(self.t, list(ids[:self.n_m]))
                       + self.smon.reports(self.t, list(ids[self.n_m:])))
        for r in reports:
            prev = self._fdir_seen.get(r.component_id, HealthState.NOMINAL)
            if r.state is prev or r.state is HealthState.UNKNOWN:
                continue
            self._fdir_seen[r.component_id] = r.state
            if r.state is HealthState.DEGRADED:
                self._pub(EventType.FDIR_WARNING, r.component_id, **r.to_dict())
            elif r.state is HealthState.FAILED:
                self._pub(EventType.FDIR_FAILURE, r.component_id, **r.to_dict())
        key = tuple(np.round(self.health_est, 2))
        if key not in self._margin_cache:
            self._margin_cache[key] = self._hover_alloc.hover_margin(v.weight_n, self.health_est)
        self._hover_margin = self._margin_cache[key]

    # ======================================================== 6. proposals
    def _mission_manager(self) -> None:
        mode, ctx, m = self.mode, self.ctx, self.sc.mission
        heading, pitch, _ = self._att()
        ctx.alt_agl_m, ctx.airspeed_mps, ctx.landed = self.alt_meas, self.airspeed, self.landed
        pos = self.nav_sol.position_ned[:2]

        if self.trans.active:
            st = self.trans.update(self.t, self.dt, self.airspeed, math.degrees(pitch),
                                   self.alt_meas, self.sat_frac)
            self.trans_status = st
            self.acc.max_transition_alt_loss_m = max(self.acc.max_transition_alt_loss_m,
                                                     st.altitude_loss_m)
            if st.just_finished:
                self._transition_finished(st)
                return

        if mode is Mode.VTOL_TAKEOFF and self.alt_meas >= m.takeoff_alt_m - 1.0:
            self.fsm.request(Mode.TRANSITION_FW, ctx, "kalkis_irtifasi")
        elif mode is Mode.CRUISE:
            if self.waypoints_done or self.aborted:
                self.fsm.request(Mode.RETURN, ctx, "gorev_bitti")
            elif self.nav_sol.integrity_ok:
                self.fsm.request(Mode.MISSION, ctx, "gorev")
        elif mode is Mode.MISSION:
            wps = m.waypoints
            if self.wp_index < len(wps) and np.linalg.norm(pos - wps[self.wp_index]) < m.waypoint_radius_m:
                self.wp_index += 1
            if self.wp_index >= len(wps):
                self.waypoints_done = True
                self.fsm.request(Mode.RETURN, ctx, "ara_noktalar_tamam")
        elif mode is Mode.RETURN and self._dist_home() < m.back_transition_dist_m:
            self.fsm.request(Mode.TRANSITION_VTOL, ctx, "yaklasma")
        elif mode is Mode.LOITER_HOLD:
            if self.nav_sol.integrity_ok and self._link_up:
                self.fsm.request(Mode.CRUISE, ctx, "nav_geri_geldi")
            elif self.t - self._loiter_since > self.sc.safety.loiter_timeout_s:
                self.fsm.request(Mode.RETURN, ctx, "bekleme_zaman_asimi")
        elif mode in (Mode.VTOL_LAND, Mode.EMERGENCY_LAND, Mode.PARACHUTE) and self.landed:
            if mode is Mode.VTOL_LAND and self.waypoints_done and self._dist_home() < 30.0 \
                    and not self.mission_complete:
                self.mission_complete = True
                self._pub(EventType.MISSION_COMPLETE, "", distance_home_m=self._dist_home())
            self.fsm.request(Mode.DISARMED, ctx, "yere_indi")

    def _transition_finished(self, st: TransitionStatus) -> None:
        direction = "forward" if self.mode is Mode.TRANSITION_FW else "back"
        if st.phase is TransitionPhase.COMPLETED:
            self._pub(EventType.TRANSITION_COMPLETED, direction, direction=direction,
                      elapsed_s=st.elapsed_s, altitude_loss_m=st.altitude_loss_m)
            self.trans.reset()
            if self.mode is Mode.TRANSITION_FW:
                self.fc.reset_integrators()
                self.fsm.request(Mode.CRUISE, self.ctx, "gecis_tamam")
            elif self.mode is Mode.TRANSITION_VTOL:
                self.fsm.request(Mode.VTOL_LAND, self.ctx, "gecis_tamam")
            # EMERGENCY_LAND'da dikey alçalma devam eder
        else:
            self._pub(EventType.TRANSITION_ABORTED, st.abort_reason, direction=direction,
                      reason=st.abort_reason, elapsed_s=st.elapsed_s,
                      altitude_loss_m=st.altitude_loss_m)
            self.aborted = True
            self._pub(EventType.MISSION_ABORT, "gecis_iptal", reason=st.abort_reason)
            self.trans.reset()
            self.fsm.request(Mode.TRANSITION_VTOL, self.ctx, "gecis_iptal")

    def _on_mode_record(self, rec: TransitionRecord) -> None:
        if not rec.accepted:
            key = (rec.source, rec.target, rec.reason)
            if key != self._rej_key:
                self._rej_key = key
                self._pub(EventType.MODE_REJECTED, rec.diagnostic, **rec.to_dict())
            return
        self._rej_key = None
        self._pub(EventType.MODE_TRANSITION, f"{rec.source.name}->{rec.target.name}", **rec.to_dict())
        heading, pitch, _ = self._att()
        tgt = rec.target
        if tgt is Mode.TRANSITION_FW:
            self._trans_alt = self.alt_meas
            self.trans.start_forward(self.t, self.alt_meas)
            self._pub(EventType.TRANSITION_STARTED, "forward", direction="forward")
        elif tgt is Mode.TRANSITION_VTOL:
            self._start_back(heading, pitch)
        elif tgt is Mode.EMERGENCY_LAND:
            self._el_vertical = self._hover_margin > self.sc.safety.hover_margin_min
            if self._el_vertical and self.airspeed > 8.0:
                self._start_back(heading, pitch)
            else:
                self.trans.reset()
            self.hover_target = self.nav_sol.position_ned[:2].copy()
        elif tgt is Mode.PARACHUTE:
            self.trans.reset()
            self._chute_t = self.t + 1.0
        elif tgt is Mode.LOITER_HOLD:
            self._loiter_since = self.t
        elif tgt is Mode.VTOL_LAND:
            d = self._dist_home()
            self.hover_target = (self.home.copy() if d < 400.0
                                 else self.nav_sol.position_ned[:2].copy())

    def _start_back(self, heading: float, pitch: float) -> None:
        self.hover_heading = heading
        self._trans_alt = self.alt_meas
        self.trans.start_back(self.t, self.alt_meas, math.degrees(pitch))
        self._pub(EventType.TRANSITION_STARTED, "back", direction="back")

    def _proposals(self) -> tuple[Command | None, Command | None]:
        mode, m = self.mode, self.sc.mission
        if mode not in FIXED_WING_MODES:
            return None, None
        pos, vel = self.nav_sol.position_ned, self.x[3:6]
        heading = self._att()[0]
        if mode is Mode.LOITER_HOLD:
            ac = self.guid.loiter(pos, vel, m.cruise_alt_m, m.cruise_speed_mps, self.airspeed)
        else:
            if mode in (Mode.MISSION, Mode.CRUISE) and self.wp_index < len(m.waypoints) \
                    and not self.aborted:
                target = np.array(m.waypoints[self.wp_index])
            else:
                target = self.home
            ac = self.guid.to_point(pos, vel, heading, target, m.cruise_alt_m,
                                    m.cruise_speed_mps, self.airspeed)
        fd, closing = self._fence()
        sc = self.safe.command(pos, vel, heading, self.home, fd, closing,
                               self.rta.soft.min_fence_dist_m, self.airspeed)
        return ac, sc

    # ================================================================ 7. rta
    def _rta(self, ac: Command | None, sc: Command | None) -> Command | None:
        if ac is None or sc is None:
            return None
        _, pitch, bank = self._att()
        fd, closing = self._fence()
        es = EnvelopeState(self.alt_meas, self.airspeed, math.degrees(bank), math.degrees(pitch),
                           -self.x[5], fd, closing)
        d = self.rta.decide(es, ac, sc, self.t)
        if d.switched:
            et = (EventType.RTA_INTERVENTION if d.selected_source is Source.SAFETY
                  else EventType.RTA_RECOVERY)
            self._pub(et, ",".join(d.reasons), **d.to_dict())
        if d.latched and not self._rta_latched_pub:
            self._rta_latched_pub = True
            self._pub(EventType.RTA_LATCHED, ",".join(d.reasons), **d.to_dict())
        self.acc.fw_ticks += 1
        self.acc.min_envelope_margin = min(self.acc.min_envelope_margin, self.rta.soft.margin(es))
        return d.command

    # ========================================================= 8. control
    def _control(self, cmd: Command | None, R: np.ndarray, v_air_b: np.ndarray) -> np.ndarray:
        mode, v, m = self.mode, self.vehicle, self.sc.mission
        n = v.n_actuators
        if mode in _IDLE_MODES or (self.landed and mode is not Mode.VTOL_TAKEOFF):
            self.sat_frac = 0.0
            return np.zeros(n)
        q, omega = self.x[6:10], self.x[10:13]
        heading, pitch, _ = attitude_angles(R)
        climb = -self.x[5]
        v_ax = max(float(v_air_b[0]), 0.0)
        tscale = self.prop.thrust_scale(v_ax)
        tmax = float(np.sum(self.prop.tmax)) * tscale
        aero = self.aero.evaluate(self._aero_inputs(v_air_b, omega, np.zeros(4), self.envs.density))
        aero_up = -float((R @ aero.force_body)[2])
        drag = max(-float(aero.force_body[0]), 0.0)
        pos_ne, vel_ne = self.nav_sol.position_ned[:2], self.x[3:5]
        fixed_wing = mode in FIXED_WING_MODES
        trans_active = self.trans.active and self.trans_status is not None

        if trans_active and mode in (Mode.TRANSITION_FW, Mode.TRANSITION_VTOL, Mode.EMERGENCY_LAND):
            st = self.trans_status
            sp = AttitudeSetpoint(self.hover_heading, math.radians(st.pitch_cmd_deg))
            T = self.fc.vertical_thrust(self.alt_meas, climb, self._trans_alt, (-2.0, 2.0),
                                        pitch, aero_up, tmax)
        elif mode in _HOVER_MODES or (mode is Mode.EMERGENCY_LAND and self._el_vertical) \
                or mode in (Mode.TRANSITION_FW, Mode.TRANSITION_VTOL):
            if mode is Mode.VTOL_TAKEOFF:
                alt_cmd, lim = m.takeoff_alt_m, (-1.5, 2.5)
            elif mode in (Mode.TRANSITION_FW, Mode.TRANSITION_VTOL):
                alt_cmd, lim = self._trans_alt, (-1.5, 1.5)
            else:
                alt_cmd, lim = -5.0, ((-2.5 if self.alt_meas > 15.0 else -0.7), 1.0)
            tf, tl = self.fc.hover_tilt(pos_ne, vel_ne, self.hover_target, self.hover_heading)
            sp = AttitudeSetpoint(self.hover_heading, math.pi / 2 - tf, 0.0, tl)
            T = self.fc.vertical_thrust(self.alt_meas, climb, alt_cmd, lim, pitch, aero_up, tmax)
        else:
            glide = mode is Mode.EMERGENCY_LAND
            if glide:      # hover yok: sabit kanatla alçalarak iniş
                cmd = Command(0.0, -3.0 if self.alt_meas > 4.0 else 4.0, 20.0)
            elif cmd is None:
                cmd = Command(0.0, 3.0, m.cruise_speed_mps)
            vh = self.x[3:5]
            course = math.atan2(vh[1], vh[0]) if np.hypot(*vh) > 3.0 else heading
            sp = AttitudeSetpoint(course, math.radians(cmd.pitch_deg), math.radians(cmd.bank_deg))
            T = self.fc.speed_thrust(self.airspeed, cmd.airspeed_mps, pitch, drag, self.dt, tmax)
            fixed_wing = not glide       # acil süzülüşte sağlam iç motorlar da kullanılır

        M, err = self.fc.attitude_moment(q, omega, sp)
        self.att_err = err
        est_thr = np.full(self.n_m, T / self.n_m)
        cond = EffectivenessConditions(airspeed_mps=self.airspeed, density=self.envs.density,
                                       sigma=1.0 if fixed_wing else None, thrust_scale=tscale,
                                       wash_force_n=self.prop.wash_force(est_thr),
                                       fold_inner_motors=fixed_wing)
        v_des = body_to_alloc(T, M)
        res = self.alloc.allocate(v_des, self.health_est, cond)
        self.sat_frac = float(np.mean(res.saturated))
        # Kontrol kaybı: büyük tutum hatası YA DA dağıtıcının tutum momentlerini
        # (pitch + gövde roll) karşılayamaması, sürekli olarak.
        att_axes = [2, 3]
        deficit = float(np.max(np.abs(res.error[att_axes]) / np.maximum(np.abs(v_des[att_axes]), 2.0)))
        lost = err > self.sc.safety.loss_of_control_att_err_deg or deficit > 0.8
        self._loc_timer = self._loc_timer + self.dt if (not self.landed and lost) else 0.0
        return res.u

    def _aero_inputs(self, v_air_b, omega, u_surf, density) -> AeroInputs:
        v = self.vehicle
        return AeroInputs(v_air_b, omega, np.asarray(u_surf) * v.elevon_max_deflection_rad,
                          density, self._sy, v.elevon_x_m, v.elevon_area_m2,
                          v.elevon_cl_delta_per_rad)

    # ======================================================== 10. dynamics
    def _dynamics(self, st: ActuatorState, envs: EnvironmentState) -> None:
        v = self.vehicle
        u_m = st.output[:self.n_m] * self._power_factor
        u_s = st.output[self.n_m:]
        wind, rho = envs.wind_ned, envs.density
        chute = self._chute_t is not None and self.t >= self._chute_t

        def forces(x: np.ndarray) -> Wrench:
            R = quat_to_dcm(x[6:10])
            v_air_w = x[3:6] - wind
            v_air_b = R.T @ v_air_w
            thr = self.prop.thrusts(u_m, float(v_air_b[0]))
            fp, mp = self.prop.wrench_body(thr, u_s)
            aero = self.aero.evaluate(self._aero_inputs(v_air_b, x[10:13], u_s, rho))
            fw = np.zeros(3)
            if chute:
                fw = -0.5 * rho * v.parachute_cds_m2 * float(np.linalg.norm(v_air_w)) * v_air_w
            return Wrench(fp + aero.force_body, mp + aero.moment_body, fw)

        x_prev = self.x
        xn = integrate(self.dyn, forces, self.integ, x_prev, self.dt)
        if -xn[2] < 0.0 or (-xn[2] <= 0.0 and xn[5] >= 0.0):   # yerin altında ya da aşağı hareket
            if not self.landed:
                self._touchdown(xn)
            xn[2] = 0.0
            xn[3:6] = 0.0
            xn[10:13] = 0.0
            xn[6:10] = x_prev[6:10]
            self.landed = True
        elif self.landed and -xn[2] > 0.05:
            self.landed = False
        self.x = xn

    def _touchdown(self, xn: np.ndarray) -> None:
        mode = self.mode
        v_down = float(xn[5])
        v_h = float(np.hypot(xn[3], xn[4]))
        pitch = math.degrees(attitude_angles(quat_to_dcm(xn[6:10]))[1])
        if mode is Mode.PARACHUTE:
            ok, kind = v_down <= 7.0, "parachute"
        elif mode is Mode.EMERGENCY_LAND and not self._el_vertical:
            ok, kind = v_down <= 3.5, "emergency_glide"
        elif mode in (Mode.VTOL_LAND, Mode.VTOL_TAKEOFF, Mode.EMERGENCY_LAND, Mode.TRANSITION_VTOL):
            ok, kind = (v_down <= 3.0 and v_h <= 3.0 and pitch >= 60.0), "vertical"
        else:
            ok, kind = False, "uncontrolled"
        data = dict(kind=kind, vertical_speed_mps=round(v_down, 4),
                    horizontal_speed_mps=round(v_h, 4), pitch_deg=round(pitch, 3), mode=mode.name)
        if ok:
            self._pub(EventType.TOUCHDOWN, kind, **data)
        else:
            self._pub(EventType.IMPACT, kind, **data)
            self.finished = True

    # =========================================================== 11. power
    def _power(self, st: ActuatorState, envs: EnvironmentState) -> None:
        v = self.vehicle
        R = quat_to_dcm(self.x[6:10])
        v_ax = float((R.T @ (self.x[3:6] - envs.wind_ned))[0])
        thr = self.prop.thrusts(st.output[:self.n_m] * self._power_factor, v_ax)
        p_prop = self.prop.electrical_power(thr, v_ax, envs.density)
        load = p_prop + v.avionics_power_w
        split = self.em.step(self.dt, load, 0.0, emergency=self.mode not in _RESERVE_LOCKED)
        self.acc.energy_consumed_j += load * self.dt
        if split.unmet_w > 1e-6 and p_prop > 1e-6:
            self._power_factor = float(np.clip((p_prop - split.unmet_w) / p_prop, 0.0, 1.0))
        else:
            self._power_factor = 1.0

    # ===================================================== 12. contingency
    def _contingency(self) -> None:
        sf, m, ctx = self.sc.safety, self.sc.mission, self.ctx
        up, lost = self.link.update(self.t)
        if up != self._link_up:
            self._pub(EventType.LINK_LOST if not up else EventType.LINK_RESTORED, "")
        self._link_up, self._link_lost_s = up, lost

        dist = self._dist_home()
        wind_h = float(np.hypot(*self.envs.wind_ned[:2]))
        gs = max(m.cruise_speed_mps - wind_h, 8.0)
        need = (sf.cruise_power_estimate_w * dist / gs / 3600.0 + LANDING_ENERGY_WH) * 1.3
        usable = self.em.usable_energy_wh()
        if not self._energy_warned and usable < sf.energy_warning_factor * need:
            self._energy_warned = True
            self._pub(EventType.ENERGY_WARNING, "", usable_wh=round(usable, 3),
                      required_wh=round(need, 3))
            if self.mode is Mode.MISSION:
                self.aborted = True
                self._pub(EventType.MISSION_ABORT, "enerji_uyarisi", reason="enerji_uyarisi")
                self.fsm.request(Mode.RETURN, ctx, "enerji_uyarisi")
        elif self._energy_warned and usable > sf.energy_warning_factor * need * 1.1:
            self._energy_warned = False

        ctx.alt_agl_m, ctx.airspeed_mps, ctx.landed = self.alt_meas, self.airspeed, self.landed
        ctx.link_lost_s = lost
        ctx.rth_energy_ok = self.em.return_home_feasible(dist, gs, sf.cruise_power_estimate_w)
        ctx.land_energy_ok = self.em.usable_energy_wh(include_reserve=True) >= LANDING_ENERGY_WH
        ctx.nav_integrity_ok = self.nav_sol.integrity_ok
        ctx.hover_feasible = self._hover_margin > sf.hover_margin_min
        ctx.controllable = self._loc_timer < sf.loss_of_control_time_s
        d = self.cm.evaluate_detailed(self.fsm, ctx)
        if d is not None and d.accepted:
            self._pub(EventType.CONTINGENCY, d.trigger, **d.to_dict())

    # ============================================================ 14. metrics
    def _metrics(self) -> None:
        a = self.acc
        a.ticks += 1
        if self.sat_frac > 0:
            a.saturated_ticks += 1
        if not self.landed:
            a.max_attitude_error_deg = max(a.max_attitude_error_deg, self.att_err)
            a.min_altitude_airborne_m = min(a.min_altitude_airborne_m, -self.x[2])


def run_scenario(scenario: Scenario) -> SimulationResult:
    return SimulationEngine(scenario).run()
