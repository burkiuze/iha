"""Merkezi simülasyon motoru (dijital ikiz çekirdeği) — yalnızca orkestrasyon.

Her adım (tick) aşağıdaki SABİT sırayla çalışır (`TICK_ORDER`):

   1. scenario_events   arıza takvimi (FaultInjector)
   2. environment       rüzgâr, yoğunluk
   3. sensors           hava verisi (AirDataSystem, açık geri dönüşlü)
   4. navigation        konum kaynakları + bütünlük (nav periyodunda)
   5. health            FDIR (HealthSupervisor)
   6. proposals         görev yöneticisi (MissionManager) + AC/SC önerileri
   7. rta               Simplex karar -> ValidatedCommand
   8. allocation        VehicleController (kontrol yasası + dağıtım)
   9. actuators         gecikme, tepki, doyma, eyleyici arızaları
  10. dynamics          6-DOF integrasyon + yer teması; zaman burada ilerler
  11. power             elektrik yükü -> enerji yöneticisi
  12. contingency       bağlantı, enerji rezervi (ReserveMonitor), acil durum kuralları
  13. logging           anlık görüntü kaydı
  14. metrics           metrik biriktirme

Yetki zinciri (değişmez): MissionGuidance (AC) yalnızca `Command` ÖNERİR;
RuntimeAssurance bunu `ValidatedCommand`'a çevirir; VehicleController
yalnızca `ValidatedCommand` kabul eder. Eyleyicilere giden tek yol
VehicleController -> ActuatorModel'dir.

Determinizm: tüm rastgelelik `numpy.random.SeedSequence(seed)`'ten türetilen
alt üreteçlerden gelir; küresel rastgele durum kullanılmaz.

Bilinen basitleştirmeler: bkz. docs/14-simulasyon-ve-dijital-ikiz.md §12.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..aero.model import AnalyticAeroModel
from ..control.guidance import MissionGuidance, SafetyController
from ..control.transition import TransitionCoordinator, TransitionPhase, TransitionStatus
from ..core.errors import SimulationError
from ..core.events import EventBus, EventType
from ..core.frames import attitude_angles, quat_from_euler, quat_to_dcm
from ..core.types import HealthState, NavigationSolution, VehicleState
from ..modes.flight_modes import (FIXED_WING_MODES, Context, ContingencyManager,
                                  FlightModeMachine, Mode, TransitionRecord)
from ..nav.integrity import IntegrityMonitor
from ..nav.providers import NavigationSystem
from ..power.energy_manager import EnergyManager
from ..power.reserve import LANDING_ENERGY_WH, ReserveMonitor
from ..safety.rta import Command, EnvelopeState, RuntimeAssurance, Source, ValidatedCommand
from .actuators import ActuatorCommand, ActuatorModel, ActuatorState, rpm_from_output
from .airdata import AirDataSystem
from .dynamics import MassProperties, RigidBodyDynamics, Wrench, integrate, make_integrator
from .environment import ConstantEnvironment, EnvironmentState, ScriptedEnvironment
from .faults import ControllerFaultTarget, EnergyFaultTarget, FaultInjector
from .ground import classify_touchdown
from .health import HealthSupervisor
from .link import LinkModel
from .metrics import MetricsAccumulator, SimulationMetrics, compute_metrics
from .mission import MissionManager, MissionView
from .propulsion import PropulsionModel
from .recorder import SimulationRecorder
from .scenario import Scenario
from .sensors import DEFAULT_POSITION_SOURCES, SensorModel, SensorSuite, SimulatedPositionProvider
from .vehicle_control import ControlInputs, HoverPlan, VehicleController

log = logging.getLogger(__name__)

TICK_ORDER: tuple[str, ...] = (
    "scenario_events", "environment", "sensors", "navigation", "health", "proposals",
    "rta", "allocation", "actuators", "dynamics", "power", "contingency", "logging",
    "metrics",
)

_RESERVE_LOCKED = {Mode.CRUISE, Mode.MISSION, Mode.LOITER_HOLD}
_PARACHUTE_DEPLOY_DELAY_S = 1.0
_EL_VERTICAL_MIN_AIRSPEED = 8.0     # bunun üstünde dikey acil inişten önce geri geçiş
_HOME_LANDING_RADIUS_M = 400.0
_GLIDE_COMMAND = Command(0.0, -3.0, 20.0)
_GLIDE_FLARE = Command(0.0, 4.0, 20.0)
_GLIDE_FLARE_ALT_M = 4.0


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
    """Senaryoyu alt sistemleri sabit sırayla çağırarak koşturur."""

    def __init__(self, scenario: Scenario) -> None:
        scenario.validate()
        self.sc = scenario
        cfg, v, m, sf = scenario.sim, scenario.vehicle, scenario.mission, scenario.safety
        self.dt = cfg.dt_s
        self.nav_every = max(1, int(round(cfg.nav_period_s / cfg.dt_s)))
        self.vehicle = v
        self.n_m = len(v.motors)
        rngs = [np.random.default_rng(s) for s in np.random.SeedSequence(scenario.seed).spawn(9)]

        self.bus = EventBus()
        self.aero = scenario.aero_factory() if scenario.aero_factory else AnalyticAeroModel()
        meta = {**scenario.describe(), "aero_provenance": self.aero.coefficients.provenance,
                "tick_order": list(TICK_ORDER), "actuator_ids": list(v.actuator_ids)}
        self.recorder = SimulationRecorder(self.bus, cfg.snapshot_period_s, meta)

        # --- fizik
        env_cfg = scenario.environment
        self.env = (ScriptedEnvironment(list(scenario.wind_keyframes), env_cfg)
                    if scenario.wind_keyframes else ConstantEnvironment(env_cfg))
        self.env.bind_rng(rngs[0])
        self.dyn = RigidBodyDynamics(MassProperties.from_vehicle(v))
        self.integ = make_integrator(cfg.integrator)
        self.prop = PropulsionModel(v)
        n_s = len(v.surfaces)
        tau = np.array([v.motor_tau_s] * self.n_m + [v.surface_tau_s] * n_s)
        self.act = ActuatorModel(v.actuator_ids, np.array([0.0] * self.n_m + [-1.0] * n_s),
                                 np.ones(self.n_m + n_s), tau, v.actuator_latency_s, self.dt)

        # --- algı
        pos_sensors = [SensorModel(sid, [sig, sig], rngs[1 + i])
                       for i, (sid, sig) in enumerate(DEFAULT_POSITION_SOURCES.items())]
        baro = SensorModel("BARO", 0.3, rngs[5])
        pitot = SensorModel("AIRSPEED", 0.3, rngs[6])
        self.rpm_sensor = SensorModel("RPM", np.full(self.n_m, 15.0), rngs[7])
        self.sensors = SensorSuite(pos_sensors + [baro, pitot, self.rpm_sensor])
        self.airdata = AirDataSystem(pitot, baro)
        self.nav = NavigationSystem([SimulatedPositionProvider(s, self._truth_ne)
                                     for s in pos_sensors], IntegrityMonitor())

        # --- alt sistemler
        self.health = HealthSupervisor(v.actuator_ids, self.n_m, v.rpm_max, v.weight_n)
        self.em = EnergyManager()
        self.em.batt_soc = scenario.initial.battery_soc
        self.em.h2_wh *= scenario.initial.hydrogen_fraction
        self.reserve = ReserveMonitor(sf.energy_warning_factor)
        self.link = LinkModel()
        self.fsm = FlightModeMachine(clock=lambda: self.t, listener=self._on_mode_record)
        self.cm = ContingencyManager()
        self.mission = MissionManager(m, sf)
        self.guid = MissionGuidance()                  # gelişmiş kontrolcü (yalnız öneri)
        self.safe = SafetyController(m.cruise_alt_m, m.cruise_speed_mps)
        self.rta = RuntimeAssurance(horizon_s=sf.rta_horizon_s, recovery_cycles=sf.rta_recovery_cycles)
        self.trans = TransitionCoordinator()
        self.controller = VehicleController(v, sf, self.aero, self.prop)
        self.injector = FaultInjector(scenario.faults, {
            "actuator": self.act, "sensor": self.sensors, "link": self.link,
            "energy": EnergyFaultTarget(self.em), "controller": ControllerFaultTarget(self.guid),
        }, self.bus)

        # --- durum
        self.home = np.array(m.home_ne, float)
        heading0 = math.radians(m.departure_heading_deg)
        self.plan = HoverPlan(heading0, self.home.copy(), takeoff_alt_m=m.takeoff_alt_m)
        q0 = quat_from_euler(heading0, math.pi / 2, 0.0)
        self.x = np.concatenate([[self.home[0], self.home[1], 0.0], np.zeros(3), q0, np.zeros(3)])
        self.t = 0.0
        self.tick = 0
        self.landed = True
        self.finished = False
        self.timed_out = False
        self.trans_status: TransitionStatus | None = None
        self._chute_t: float | None = None
        self._power_factor = 1.0
        self._link_up = True
        self._rta_latched_pub = False
        self._rej_key: tuple | None = None
        # İlk navigasyon çözümünden önce bütünlük VARSAYILMAZ (unknown != healthy).
        self.nav_sol = NavigationSolution(np.array([*self.home, 0.0]), np.zeros(3), 0.0,
                                          float("inf"), (), (), (), False, 0.0)
        self._nav_initialized = False
        self.ctx = Context(preflight_ok=True)
        self.acc = MetricsAccumulator()
        self._started = False

    # ================================================================== API
    @property
    def mode(self) -> Mode:
        return self.fsm.mode

    @property
    def airspeed(self) -> float:
        return self.airdata.airspeed_mps

    @property
    def alt_meas(self) -> float:
        return self.airdata.altitude_m

    def run(self) -> SimulationResult:
        self.start()
        while not self.finished and self.t < self.sc.duration_s - 1e-9:
            self.step()
        self.timed_out = not self.finished
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
        """Tek adım. Sayısal hata `sim_failed` olayıyla kaydedilip yeniden fırlatılır."""
        try:
            self._step()
        except SimulationError as e:
            self._pub(EventType.SIM_FAILED, str(e), reason=str(e), tick=self.tick)
            self.finished = True
            raise

    def _step(self) -> None:
        dt = self.dt
        self.injector.update(self.t)                                        # 1
        envs = self.env.update(self.t, dt, self.x[0:3])                     # 2
        self.envs = envs
        R = quat_to_dcm(self.x[6:10])                                       # 3
        v_air_b = R.T @ (self.x[3:6] - envs.wind_ned)
        for ch in self.airdata.update(self.t, dt, float(np.linalg.norm(v_air_b)), -self.x[2],
                                      self.x[3:6]):
            et = EventType.SENSOR_DEGRADED if ch.degraded else EventType.SENSOR_RESTORED
            self._pub(et, ch.sensor_id, component=ch.sensor_id, fallback=ch.fallback,
                      reason="olcum_gecersiz" if ch.degraded else "olcum_geri_geldi")
        if self.tick % self.nav_every == 0:                                 # 4
            self._navigation()
        self._health()                                                      # 5
        self._mission_step()                                                # 6
        ac, sc = self._proposals()
        validated = self._rta(ac, sc)                                       # 7
        u = self.controller.compute(self._control_inputs(R, v_air_b, validated),   # 8
                                    self.plan, self.sc.mission.cruise_speed_mps)
        st = self.act.step(ActuatorCommand(u, self.t))                      # 9
        self._dynamics(st, envs)                                            # 10
        self.t = round(self.t + dt, 9)
        self.tick += 1
        if self.finished:
            return
        self._power(st, envs)                                               # 11
        self._contingency()                                                 # 12
        self.recorder.maybe_snapshot(self.t, self._snapshot())              # 13
        self._metrics()                                                     # 14
        if self.mode is Mode.DISARMED and self.sc.sim.stop_when_disarmed:
            self.finished = True

    def finish(self) -> SimulationResult:
        vs = self.vehicle_state()
        self.recorder.maybe_snapshot(self.t, self._snapshot(), force=True)
        self.bus.publish(EventType.SIM_FINISHED, self.t, "engine", self.mode.name,
                         timed_out=self.timed_out)
        impact = any(e["type"] == EventType.IMPACT.value for e in self.recorder.events)
        metrics = compute_metrics(
            self.recorder.events, self.acc, self.t, self.mode.name, self.mission.completed,
            [f.to_dict() for f in self.sc.faults], dict(self.injector.activation_times),
            self.em.usable_energy_wh(), self.em.reserve_energy_wh(),
            self.mission.outcome_reason(self.mode.name, impact, self.timed_out))
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
                            self.health.health.copy(), self.mode.name, self.landed)

    def _snapshot(self) -> dict[str, Any]:
        s = self.vehicle_state().snapshot()
        pl = self.nav_sol.protection_level_m
        s.update({"rta": self.rta.source.value,
                  "nav_pl": round(pl, 3) if math.isfinite(pl) else None,
                  "nav_used": list(self.nav_sol.sources_used),
                  "sat": round(self.controller.saturation_fraction, 4),
                  "power_factor": round(self._power_factor, 4),
                  "airdata_degraded": sorted(k for k, d in self.airdata.degraded.items() if d),
                  "transition": None if self.trans_status is None else self.trans_status.phase.value})
        return s

    def _fence(self) -> tuple[float, float]:
        rel = self.nav_sol.position_ned[:2] - self.home
        r = float(np.linalg.norm(rel))
        closing = float(np.dot(rel, self.x[3:5]) / r) if r > 1e-6 else 0.0
        return self.sc.safety.geofence_radius_m - r, closing

    def _dist_home(self) -> float:
        return self.mission.dist_home(self.nav_sol.position_ned[:2])

    # ================================================================ 4. nav
    def _navigation(self) -> None:
        prev = self.nav_sol
        sol = self.nav.update(self.t, self.alt_meas, self.x[3:6])
        self.nav_sol = sol
        first = not self._nav_initialized
        self._nav_initialized = True
        for s in sorted(set(sol.sources_unavailable) - set(prev.sources_unavailable)):
            self._pub(EventType.NAV_SOURCE_UNAVAILABLE, s, source=s, component=s,
                      reason="olcum_yok_ya_da_gecersiz")
        r = self.nav.last_integrity
        for s in sorted(set(sol.sources_rejected) - set(prev.sources_rejected)):
            self._pub(EventType.NAV_SOURCE_REJECTED, s, source=s, component=s,
                      reason="tutarlilik_testi_dislama",
                      test_statistic=None if r is None else round(r.test_statistic, 4),
                      threshold=None if r is None else round(r.threshold, 4),
                      sources_used=list(sol.sources_used),
                      protection_level_m=round(sol.protection_level_m, 4))
        if first:
            return                     # ilk çözüm: "geri geldi" değil, ilk edinim
        if prev.integrity_ok and not sol.integrity_ok:
            reason = ("kaynak_yetersiz" if len(sol.sources_used) < self.nav.min_sources_for_integrity
                      else "koruma_seviyesi_alarm_limitini_asti")
            self._pub(EventType.NAV_INTEGRITY_LOST, reason, reason=reason, solution=sol.to_dict())
        elif not prev.integrity_ok and sol.integrity_ok:
            self._pub(EventType.NAV_INTEGRITY_RESTORED, "", reason="tutarli_kaynak_kumesi",
                      solution=sol.to_dict())

    # ============================================================= 5. health
    def _health(self) -> None:
        st = self.act.last
        if st is None:
            return
        pf = self._power_factor
        meas = self.rpm_sensor.measure(rpm_from_output(st.output[:self.n_m] * pf,
                                                       self.vehicle.rpm_max), self.t)
        rpm = meas.value if meas.valid else None
        for r in self.health.update(st, rpm, pf, self.t, airborne=not self.landed):
            et = EventType.FDIR_WARNING if r.state is HealthState.DEGRADED else EventType.FDIR_FAILURE
            self._pub(et, r.component_id, component=r.component_id, **r.to_dict(),
                      monitor=self.health.details(r.component_id))

    # ======================================================== 6. proposals
    def _mission_step(self) -> None:
        ctx = self.ctx
        _, pitch, _ = self._att()
        ctx.alt_agl_m, ctx.airspeed_mps, ctx.landed = self.alt_meas, self.airspeed, self.landed
        if self.trans.active:
            st = self.trans.update(self.t, self.dt, self.airspeed, math.degrees(pitch),
                                   self.alt_meas, self.controller.saturation_fraction)
            self.trans_status = st
            self.acc.max_transition_alt_loss_m = max(self.acc.max_transition_alt_loss_m,
                                                     st.altitude_loss_m)
            if st.just_finished:
                self._transition_finished(st)
                return
        req, completed_now = self.mission.step(MissionView(
            self.mode, self.t, self.nav_sol.position_ned[:2], self.alt_meas,
            self.nav_sol.integrity_ok, self._link_up, self.landed))
        if completed_now:
            self._pub(EventType.MISSION_COMPLETE, "", reason="ara_noktalar_tamam_ve_eve_inis",
                      distance_home_m=round(self._dist_home(), 3))
        if req is not None:
            self.fsm.request(req.target, ctx, req.reason)

    def _transition_finished(self, st: TransitionStatus) -> None:
        direction = "forward" if self.mode is Mode.TRANSITION_FW else "back"
        info = dict(direction=direction, elapsed_s=round(st.elapsed_s, 4),
                    altitude_loss_m=round(st.altitude_loss_m, 4))
        self.trans.reset()
        if st.phase is TransitionPhase.COMPLETED:
            self._pub(EventType.TRANSITION_COMPLETED, direction, reason="gecis_olcutleri_saglandi",
                      **info)
            if self.mode is Mode.TRANSITION_FW:
                self.controller.reset_integrators()
                self.fsm.request(Mode.CRUISE, self.ctx, "gecis_tamam")
            elif self.mode is Mode.TRANSITION_VTOL:
                self.fsm.request(Mode.VTOL_LAND, self.ctx, "gecis_tamam")
            return
        self._pub(EventType.TRANSITION_ABORTED, st.abort_reason, reason=st.abort_reason, **info)
        if self.mission.abort(f"gecis_iptal:{st.abort_reason}"):
            self._pub(EventType.MISSION_ABORT, "gecis_iptal", reason=f"gecis_iptal:{st.abort_reason}")
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
        self.mission.on_mode_entered(tgt, self.t)
        if tgt is Mode.TRANSITION_FW:
            self.plan.transition_alt_m = self.alt_meas
            self.trans.start_forward(self.t, self.alt_meas)
            self._pub(EventType.TRANSITION_STARTED, "forward", direction="forward")
        elif tgt is Mode.TRANSITION_VTOL:
            self._start_back(heading, pitch)
        elif tgt is Mode.EMERGENCY_LAND:
            self.plan.emergency_vertical = self.health.hover_margin > self.sc.safety.hover_margin_min
            if self.plan.emergency_vertical and self.airspeed > _EL_VERTICAL_MIN_AIRSPEED:
                self._start_back(heading, pitch)
            else:
                self.trans.reset()
            self.plan.target_ne = self.nav_sol.position_ned[:2].copy()
        elif tgt is Mode.PARACHUTE:
            self.trans.reset()
            self._chute_t = self.t + _PARACHUTE_DEPLOY_DELAY_S
        elif tgt is Mode.VTOL_LAND:
            self.plan.target_ne = (self.home.copy() if self._dist_home() < _HOME_LANDING_RADIUS_M
                                   else self.nav_sol.position_ned[:2].copy())

    def _start_back(self, heading: float, pitch: float) -> None:
        self.plan.heading_rad = heading
        self.plan.transition_alt_m = self.alt_meas
        self.trans.start_back(self.t, self.alt_meas, math.degrees(pitch))
        self._pub(EventType.TRANSITION_STARTED, "back", direction="back")

    def _proposals(self) -> tuple[Command | None, Command | None]:
        """Gelişmiş kontrolcü (AC) ve güvenlik kontrolcüsü (SC) ÖNERİLERİ."""
        mode, m = self.mode, self.sc.mission
        pos, vel = self.nav_sol.position_ned, self.x[3:6]
        heading = self._att()[0]
        fd, closing = self._fence()
        sc = self.safe.command(pos, vel, heading, self.home, fd, closing,
                               self.rta.soft.min_fence_dist_m, self.airspeed)
        if mode not in FIXED_WING_MODES:
            return None, sc
        if mode is Mode.LOITER_HOLD:
            ac = self.guid.loiter(pos, vel, m.cruise_alt_m, m.cruise_speed_mps, self.airspeed)
        else:
            ac = self.guid.to_point(pos, vel, heading, self.mission.guidance_target(mode),
                                    m.cruise_alt_m, m.cruise_speed_mps, self.airspeed)
        return ac, sc

    # ================================================================ 7. rta
    def _rta(self, ac: Command | None, sc: Command | None) -> ValidatedCommand | None:
        mode = self.mode
        if mode is Mode.EMERGENCY_LAND and not self.plan.emergency_vertical:
            glide = _GLIDE_FLARE if self.alt_meas <= _GLIDE_FLARE_ALT_M else _GLIDE_COMMAND
            return self.rta.safety_only(glide, self.t, "acil_suzulus")
        if ac is None:
            return None                 # askı/geçiş: RTA zarfı tanımsız, komut yok
        _, pitch, bank = self._att()
        fd, closing = self._fence()
        es = EnvelopeState(self.alt_meas, self.airspeed, math.degrees(bank), math.degrees(pitch),
                           -self.x[5], fd, closing)
        d = self.rta.decide(es, ac, sc, self.t)
        if d.switched:
            et = (EventType.RTA_INTERVENTION if d.selected_source is Source.SAFETY
                  else EventType.RTA_RECOVERY)
            self._pub(et, ",".join(d.reasons), component="rta",
                      reason=",".join(d.reasons) or "zarf_icinde_kalici", **d.to_dict())
        if d.latched and not self._rta_latched_pub:
            self._rta_latched_pub = True
            self._pub(EventType.RTA_LATCHED, ",".join(d.reasons), component="rta",
                      reason="sert_zarf_ihlali", **d.to_dict())
        self.acc.fw_ticks += 1
        self.acc.min_envelope_margin = min(self.acc.min_envelope_margin, self.rta.soft.margin(es))
        return d.validated

    # ========================================================= 8. control
    def _control_inputs(self, R: np.ndarray, v_air_b: np.ndarray,
                        validated: ValidatedCommand | None) -> ControlInputs:
        return ControlInputs(
            self.mode, self.landed, self.x[6:10], self.x[10:13], R, v_air_b, self.x[3:6],
            self.nav_sol.position_ned[:2], self.alt_meas, self.airspeed, self.envs.density,
            self.health.health, self.trans_status if self.trans.active else None,
            validated, self.dt)

    # ======================================================== 10. dynamics
    def _dynamics(self, st: ActuatorState, envs: EnvironmentState) -> None:
        v = self.vehicle
        u_m = st.output[:self.n_m] * self._power_factor
        u_s = st.output[self.n_m:]
        wind, rho = envs.wind_ned, envs.density
        chute = self._chute_t is not None and self.t >= self._chute_t
        ctrl = self.controller

        def forces(x: np.ndarray) -> Wrench:
            R = quat_to_dcm(x[6:10])
            v_air_w = x[3:6] - wind
            v_air_b = R.T @ v_air_w
            thr = self.prop.thrusts(u_m, float(v_air_b[0]))
            fp, mp = self.prop.wrench_body(thr, u_s)
            aero = self.aero.evaluate(ctrl.aero_inputs(v_air_b, x[10:13], u_s, rho))
            fw = np.zeros(3)
            if chute:
                fw = -0.5 * rho * v.parachute_cds_m2 * float(np.linalg.norm(v_air_w)) * v_air_w
            return Wrench(fp + aero.force_body, mp + aero.moment_body, fw)

        x_prev = self.x
        xn = integrate(self.dyn, forces, self.integ, x_prev, self.dt)
        if -xn[2] < 0.0 or (-xn[2] <= 0.0 and xn[5] >= 0.0):   # yerin altında ya da aşağı hareket
            if not self.landed:
                pitch = math.degrees(attitude_angles(quat_to_dcm(xn[6:10]))[1])
                td = classify_touchdown(self.mode, self.plan.emergency_vertical, float(xn[5]),
                                        float(np.hypot(xn[3], xn[4])), pitch)
                self._pub(EventType.TOUCHDOWN if td.safe else EventType.IMPACT, td.kind, **td.to_dict())
                if not td.safe:
                    self.finished = True
            xn[2] = 0.0
            xn[3:6] = 0.0
            xn[10:13] = 0.0
            xn[6:10] = x_prev[6:10]
            self.landed = True
        elif self.landed and -xn[2] > 0.05:
            self.landed = False
        self.x = xn

    # =========================================================== 11. power
    def _power(self, st: ActuatorState, envs: EnvironmentState) -> None:
        R = quat_to_dcm(self.x[6:10])
        v_ax = float((R.T @ (self.x[3:6] - envs.wind_ned))[0])
        thr = self.prop.thrusts(st.output[:self.n_m] * self._power_factor, v_ax)
        p_prop = self.prop.electrical_power(thr, v_ax, envs.density)
        load = p_prop + self.vehicle.avionics_power_w
        split = self.em.step(self.dt, load, 0.0, emergency=self.mode not in _RESERVE_LOCKED)
        self.acc.energy_consumed_j += load * self.dt
        if split.unmet_w > 1e-6 and p_prop > 1e-6:
            self._power_factor = min(max((p_prop - split.unmet_w) / p_prop, 0.0), 1.0)
        else:
            self._power_factor = 1.0

    # ===================================================== 12. contingency
    def _contingency(self) -> None:
        sf, m, ctx = self.sc.safety, self.sc.mission, self.ctx
        up, lost = self.link.update(self.t)
        if up != self._link_up:
            self._pub(EventType.LINK_LOST if not up else EventType.LINK_RESTORED, "",
                      component="link:c2", reason="c2_yok" if not up else "c2_geri_geldi")
        self._link_up = up

        dist = self._dist_home()
        gs = max(m.cruise_speed_mps - float(np.hypot(*self.envs.wind_ned[:2])), 8.0)
        usable = self.em.usable_energy_wh()
        a = self.reserve.assess(usable, dist, gs, sf.cruise_power_estimate_w)
        if a.warn_now:
            self._pub(EventType.ENERGY_WARNING, "", component="energy", **a.to_dict())
            if self.mode is Mode.MISSION and self.mission.abort("enerji_uyarisi"):
                self._pub(EventType.MISSION_ABORT, "enerji_uyarisi", reason="enerji_uyarisi")
                self.fsm.request(Mode.RETURN, ctx, "enerji_uyarisi")

        energy_known = math.isfinite(usable)
        ctx.alt_agl_m, ctx.airspeed_mps, ctx.landed = self.alt_meas, self.airspeed, self.landed
        ctx.link_lost_s = lost
        ctx.rth_energy_ok = energy_known and self.em.return_home_feasible(
            dist, gs, sf.cruise_power_estimate_w)
        ctx.land_energy_ok = energy_known and \
            self.em.usable_energy_wh(include_reserve=True) >= LANDING_ENERGY_WH
        ctx.nav_integrity_ok = self.nav_sol.integrity_ok
        ctx.hover_feasible = self.health.hover_margin > sf.hover_margin_min
        ctx.controllable = self.controller.controllable
        d = self.cm.evaluate_detailed(self.fsm, ctx)
        if d is not None and d.accepted:
            self._pub(EventType.CONTINGENCY, d.trigger, component="contingency_manager",
                      **d.to_dict())

    # ============================================================ 14. metrics
    def _metrics(self) -> None:
        a = self.acc
        a.ticks += 1
        if self.controller.saturation_fraction > 0:
            a.saturated_ticks += 1
        if not self.landed:
            a.max_attitude_error_deg = max(a.max_attitude_error_deg,
                                           self.controller.attitude_error_deg)
            a.min_altitude_airborne_m = min(a.min_altitude_airborne_m, -self.x[2])


def run_scenario(scenario: Scenario) -> SimulationResult:
    return SimulationEngine(scenario).run()
