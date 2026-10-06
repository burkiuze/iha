"""Kontrol soyutlaması: uçuş moduna göre kontrol yasası seçimi + dağıtım.

Sorumluluk: (mod, durum, geçiş durumu, RTA'dan geçmiş komut) -> eyleyici
komutu. Güdüm/YZ katmanını bilmez ve ondan komut almaz.

Mimari değişmez: sabit kanat yasası yalnızca `safety.rta.ValidatedCommand`
kabul eder. Ham `Command` verilirse `SafetyInvariantError` fırlatılır; böylece
gelişmiş kontrolcünün RTA'yı atlayarak eyleyicilere ulaşabileceği bir kod
yolu yoktur (testlerle doğrulanır).

Kontrol kaybı izleyicisi: büyük tutum hatası ya da dağıtıcının tutum
momentlerini karşılayamaması belirli süre sürerse `controllable=False`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..aero.model import AeroInputs, AerodynamicModel
from ..control.allocation import AllocationResult, ScheduledAllocator
from ..control.effectiveness import (EffectivenessConditions, ScheduledEffectiveness,
                                     body_to_alloc)
from ..control.flight_controller import AttitudeSetpoint, FlightController
from ..control.transition import TransitionStatus
from ..core.config import SafetyConfig, VehicleConfig
from ..core.errors import SafetyInvariantError, SimulationError
from ..core.frames import attitude_angles
from ..modes.flight_modes import FIXED_WING_MODES, Mode
from ..safety.rta import ValidatedCommand
from .propulsion import PropulsionModel

IDLE_MODES = frozenset({Mode.PREFLIGHT, Mode.ARMED, Mode.DISARMED, Mode.PARACHUTE})
HOVER_MODES = frozenset({Mode.VTOL_TAKEOFF, Mode.VTOL_LAND})
# Allocation ekseni indeksleri (askı çerçevesi): pitch = My_h, gövde roll = Mz_h
_ATTITUDE_AXES = [2, 3]
_DEFICIT_LIMIT = 0.8           # karşılanamayan tutum momenti oranı


@dataclass(frozen=True)
class ControlInputs:
    """Kontrolcünün bir adımda gördüğü her şey (salt okunur)."""
    mode: Mode
    landed: bool
    q: np.ndarray
    omega: np.ndarray
    R: np.ndarray
    v_air_body: np.ndarray
    vel_ned: np.ndarray
    pos_ne_nav: np.ndarray
    altitude_m: float
    airspeed_mps: float
    density: float
    health: np.ndarray
    transition: TransitionStatus | None
    command: ValidatedCommand | None
    dt: float


@dataclass
class HoverPlan:
    """Askı/geçiş yasalarının durumlu hedefleri (görev yöneticisi günceller)."""
    heading_rad: float
    target_ne: np.ndarray
    transition_alt_m: float = 0.0
    emergency_vertical: bool = True
    takeoff_alt_m: float = 50.0


class VehicleController:
    def __init__(self, vehicle: VehicleConfig, safety: SafetyConfig,
                 aero: AerodynamicModel, propulsion: PropulsionModel) -> None:
        self.v = vehicle
        self.safety = safety
        self.aero = aero
        self.prop = propulsion
        self.fc = FlightController(vehicle)
        self.alloc = ScheduledAllocator(ScheduledEffectiveness(vehicle))
        self._sy = np.array([s.y for s in vehicle.surfaces])
        self.loss_of_control_timer = 0.0
        self.saturation_fraction = 0.0
        self.attitude_error_deg = 0.0
        self.last_allocation: AllocationResult | None = None

    # ---------------------------------------------------------------------
    def aero_inputs(self, v_air_b: np.ndarray, omega: np.ndarray, u_surf: np.ndarray,
                    density: float) -> AeroInputs:
        v = self.v
        return AeroInputs(v_air_b, omega, np.asarray(u_surf) * v.elevon_max_deflection_rad,
                          density, self._sy, v.elevon_x_m, v.elevon_area_m2,
                          v.elevon_cl_delta_per_rad)

    @property
    def controllable(self) -> bool:
        return self.loss_of_control_timer < self.safety.loss_of_control_time_s

    def compute(self, ci: ControlInputs, plan: HoverPlan, cruise_speed_mps: float) -> np.ndarray:
        """Bir adımın eyleyici komutunu üretir (n_actuators,)."""
        mode = ci.mode
        if mode in IDLE_MODES or (ci.landed and mode is not Mode.VTOL_TAKEOFF):
            self.saturation_fraction = 0.0
            self.loss_of_control_timer = 0.0
            return np.zeros(self.v.n_actuators)
        if ci.command is not None and not isinstance(ci.command, ValidatedCommand):
            raise SafetyInvariantError("kontrol katmanı yalnızca RTA'dan geçmiş komut kabul eder")

        heading, pitch, _ = attitude_angles(ci.R)
        climb = -float(ci.vel_ned[2])
        v_ax = max(float(ci.v_air_body[0]), 0.0)
        tscale = self.prop.thrust_scale(v_ax)
        tmax = float(np.sum(self.prop.tmax)) * tscale
        aero = self.aero.evaluate(self.aero_inputs(ci.v_air_body, ci.omega, np.zeros(4), ci.density))
        aero_up = -float((ci.R @ aero.force_body)[2])
        drag = max(-float(aero.force_body[0]), 0.0)
        fixed_wing = mode in FIXED_WING_MODES
        st = ci.transition

        if st is not None and mode in (Mode.TRANSITION_FW, Mode.TRANSITION_VTOL, Mode.EMERGENCY_LAND):
            sp = AttitudeSetpoint(plan.heading_rad, math.radians(st.pitch_cmd_deg))
            T = self.fc.vertical_thrust(ci.altitude_m, climb, plan.transition_alt_m, (-2.0, 2.0),
                                        pitch, aero_up, tmax)
        elif mode in HOVER_MODES or mode in (Mode.TRANSITION_FW, Mode.TRANSITION_VTOL) \
                or (mode is Mode.EMERGENCY_LAND and plan.emergency_vertical):
            if mode is Mode.VTOL_TAKEOFF:
                alt_cmd, lim = plan.takeoff_alt_m, (-1.5, 2.5)
            elif mode in (Mode.TRANSITION_FW, Mode.TRANSITION_VTOL):
                alt_cmd, lim = plan.transition_alt_m, (-1.5, 1.5)
            else:   # dikey iniş: yüksekte hızlı, yere yakın yavaş alçal
                alt_cmd, lim = -5.0, ((-2.5 if ci.altitude_m > 15.0 else -0.7), 1.0)
            tf, tl = self.fc.hover_tilt(ci.pos_ne_nav, ci.vel_ned[:2], plan.target_ne,
                                        plan.heading_rad)
            sp = AttitudeSetpoint(plan.heading_rad, math.pi / 2 - tf, 0.0, tl)
            T = self.fc.vertical_thrust(ci.altitude_m, climb, alt_cmd, lim, pitch, aero_up, tmax)
        else:
            if ci.command is None:
                raise SafetyInvariantError(f"{mode.name}: sabit kanat yasası doğrulanmış komut olmadan çalışmaz")
            cmd = ci.command.command
            vh = ci.vel_ned[:2]
            course = math.atan2(vh[1], vh[0]) if float(np.hypot(*vh)) > 3.0 else heading
            sp = AttitudeSetpoint(course, math.radians(cmd.pitch_deg), math.radians(cmd.bank_deg))
            T = self.fc.speed_thrust(ci.airspeed_mps, cmd.airspeed_mps, pitch, drag, ci.dt, tmax)
            fixed_wing = mode is not Mode.EMERGENCY_LAND   # acil süzülüşte iç motorlar da açık

        M, err = self.fc.attitude_moment(ci.q, ci.omega, sp)
        self.attitude_error_deg = err
        est_thr = np.full(len(self.v.motors), T / len(self.v.motors))
        cond = EffectivenessConditions(airspeed_mps=ci.airspeed_mps, density=ci.density,
                                       sigma=1.0 if fixed_wing else None, thrust_scale=tscale,
                                       wash_force_n=self.prop.wash_force(est_thr),
                                       fold_inner_motors=fixed_wing)
        v_des = body_to_alloc(T, M)
        if not np.all(np.isfinite(v_des)):
            raise SimulationError(f"{mode.name}: kontrol isteği sonlu değil (durum/model bozulması)")
        res = self.alloc.allocate(v_des, ci.health, cond)
        self.last_allocation = res
        self.saturation_fraction = float(np.mean(res.saturated))
        deficit = float(np.max(np.abs(res.error[_ATTITUDE_AXES])
                               / np.maximum(np.abs(v_des[_ATTITUDE_AXES]), 2.0)))
        lost = err > self.safety.loss_of_control_att_err_deg or deficit > _DEFICIT_LIMIT
        self.loss_of_control_timer = self.loss_of_control_timer + ci.dt if lost else 0.0
        return res.u

    def reset_integrators(self) -> None:
        self.fc.reset_integrators()
