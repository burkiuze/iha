"""Vehicle Health Manager: FDIR omurgasının birleşim noktası.

Sekiz alan FDIR raporu (sensör, navigasyon, FCC, motor, eyleyici, enerji,
haberleşme, görev bilgisayarı) + türetilmiş kontrol otoritesi alanı
birleştirilir:

  * alan durumları: NOMINAL < DEGRADED < UNKNOWN < FAILED (önem sırası)
  * araç seviyesi (`VehicleHealthLevel`) + gerekçeler (reasons[]):

      CRITICAL     kontrol kaybı, askı yedekliliği yok, hiç FCC şeridi yok
      CONTINGENCY  diğer FAILED alanlar (nav bütünlüğü, C2, güç, tek şerit,
                   görev bilgisayarı, yüzeylerin tamamı, geri dönüşsüz sensör)
      UNKNOWN      herhangi bir alan bilinmiyor
      DEGRADED     herhangi bir alan bozulmuş
      NOMINAL      hepsi nominal

UNKNOWN hiçbir zaman NOMINAL kabul edilmez; DEGRADED'den daha ağırdır
(bilinmeyen bir işlevin çalıştığına güvenilmez).

Model yalnızca DEĞERLENDİRİR: mod değiştirmez, eyleyici sürmez.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..core.types import HealthState, NavigationSolution
from .lanes import LaneState
from .reports import (FdirDomain, FdirReport, actuator_fdir, communication_fdir, energy_fdir,
                      fcc_fdir, legacy_sensor_fdir, mission_computer_fdir, motor_fdir,
                      navigation_fdir, sensor_fdir)

SEVERITY = {HealthState.NOMINAL: 0, HealthState.DEGRADED: 1, HealthState.UNKNOWN: 2,
            HealthState.FAILED: 3}


class Domain(str, Enum):
    SENSORS = "sensors"
    NAVIGATION = "navigation"
    FCC = "fcc"
    MOTORS = "motors"
    ACTUATORS = "actuators"          # kontrol yüzeyleri (elevonlar)
    ENERGY = "energy"
    POWER = "energy"                 # geriye dönük uyumlu takma ad
    COMMUNICATION = "communication"
    MISSION_COMPUTER = "mission_computer"
    CONTROL = "control"              # türetilmiş: kontrol otoritesi


class VehicleHealthLevel(str, Enum):
    NOMINAL = "nominal"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"
    CONTINGENCY = "contingency"
    CRITICAL = "critical"


LEVEL_SEVERITY = {VehicleHealthLevel.NOMINAL: 0, VehicleHealthLevel.DEGRADED: 1,
                  VehicleHealthLevel.UNKNOWN: 2, VehicleHealthLevel.CONTINGENCY: 3,
                  VehicleHealthLevel.CRITICAL: 4}

_FDIR_TO_DOMAIN = {FdirDomain.SENSOR: Domain.SENSORS, FdirDomain.NAVIGATION: Domain.NAVIGATION,
                   FdirDomain.FCC: Domain.FCC, FdirDomain.MOTOR: Domain.MOTORS,
                   FdirDomain.ACTUATOR: Domain.ACTUATORS, FdirDomain.ENERGY: Domain.ENERGY,
                   FdirDomain.COMMUNICATION: Domain.COMMUNICATION,
                   FdirDomain.MISSION_COMPUTER: Domain.MISSION_COMPUTER}

# Simülasyonda hiç modellenmeyen alanlar ("modellenmedi" != "sağlıklı").
NOT_MODELED: tuple[str, ...] = ("thermal", "imu_redundancy")


@dataclass(frozen=True)
class DomainHealth:
    domain: Domain
    state: HealthState
    reason: str
    components: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {"domain": self.domain.value, "state": self.state.value, "reason": self.reason,
                "components": list(self.components)}


@dataclass(frozen=True)
class VehicleHealth:
    overall: HealthState
    domains: tuple[DomainHealth, ...]
    level: VehicleHealthLevel = VehicleHealthLevel.UNKNOWN
    reasons: tuple[str, ...] = ()
    reports: tuple[FdirReport, ...] = ()

    def domain(self, d: Domain) -> DomainHealth:
        return next(x for x in self.domains if x.domain is d)

    def signature(self) -> tuple:
        return (self.overall, self.level) + tuple((d.domain, d.state, d.reason) for d in self.domains)

    def to_dict(self) -> dict:
        return {"overall": self.overall.value, "level": self.level.value,
                "reasons": list(self.reasons), "domains": [d.to_dict() for d in self.domains],
                "fdir_reports": [r.to_dict() for r in self.reports],
                "not_modeled": list(NOT_MODELED)}


def worst(states: list[HealthState]) -> HealthState:
    return max(states, key=SEVERITY.__getitem__) if states else HealthState.UNKNOWN


def classify(domains: tuple[DomainHealth, ...]) -> tuple[VehicleHealthLevel, tuple[str, ...]]:
    """Alan durumlarından araç seviyesi + gerekçeler."""
    by = {d.domain: d for d in domains}
    reasons = tuple(f"{d.domain.value}:{d.state.value}:{d.reason}" for d in domains
                    if d.state is not HealthState.NOMINAL)
    failed = {d.domain for d in domains if d.state is HealthState.FAILED}
    critical = (Domain.CONTROL in failed or Domain.MOTORS in failed
                or (Domain.FCC in failed and by[Domain.FCC].reason == "serit_yok"))
    if critical:
        return VehicleHealthLevel.CRITICAL, reasons
    if failed:
        return VehicleHealthLevel.CONTINGENCY, reasons
    if any(d.state is HealthState.UNKNOWN for d in domains):
        return VehicleHealthLevel.UNKNOWN, reasons
    if reasons:
        return VehicleHealthLevel.DEGRADED, reasons
    return VehicleHealthLevel.NOMINAL, ()


class VehicleHealthModel:
    """Vehicle Health Manager (geriye dönük uyumlu ad)."""

    def assess(self, *, actuator_states: dict[str, HealthState], hover_feasible: bool,
               airborne: bool, degraded_sensors: list[str], nav: NavigationSolution | None,
               nav_initialized: bool, energy_health: float, usable_energy_wh: float,
               energy_warning: bool, unmet_power_w: float, link_up: bool,
               controllable: bool, sensor_states: dict[str, HealthState] | None = None,
               lane_states: dict[str, LaneState] | None = None,
               proposal_ok: bool | None = None, proposal_rejected_s: float = 0.0,
               motor_ids: frozenset[str] | None = None) -> VehicleHealth:
        is_motor = (lambda k: k in motor_ids) if motor_ids is not None else (lambda k: k.startswith("M"))
        motors = {k: s for k, s in actuator_states.items() if is_motor(k)}
        surfaces = {k: s for k, s in actuator_states.items() if not is_motor(k)}
        reports = (
            sensor_fdir(sensor_states, airborne) if sensor_states is not None
            else legacy_sensor_fdir(degraded_sensors),
            navigation_fdir(nav, nav_initialized),
            fcc_fdir(lane_states),
            motor_fdir(motors, hover_feasible, airborne),
            actuator_fdir(surfaces),
            energy_fdir(energy_health, usable_energy_wh, energy_warning, unmet_power_w),
            communication_fdir(link_up),
            mission_computer_fdir(proposal_ok, proposal_rejected_s),
        )
        domains = tuple(DomainHealth(_FDIR_TO_DOMAIN[r.domain], r.health_state, r.reason,
                                     r.fault_isolated) for r in reports)
        domains += (self._control(controllable, hover_feasible),)
        level, reasons = classify(domains)
        return VehicleHealth(worst([d.state for d in domains]), domains, level, reasons, reports)

    @staticmethod
    def _control(controllable: bool, hover_ok: bool) -> DomainHealth:
        if not controllable:
            return DomainHealth(Domain.CONTROL, HealthState.FAILED, "kontrol_kaybi")
        if not hover_ok:
            return DomainHealth(Domain.CONTROL, HealthState.DEGRADED, "aski_otoritesi_yok")
        return DomainHealth(Domain.CONTROL, HealthState.NOMINAL, "nominal")


VehicleHealthManager = VehicleHealthModel
