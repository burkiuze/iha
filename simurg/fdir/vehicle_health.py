"""Araç sağlık modeli (Vehicle Health Model): FDIR omurgasının birleşim noktası.

Alan (domain) bazında sağlık durumu üretir ve en kötüsünü araç durumu
olarak birleştirir. Önem sırası: NOMINAL < DEGRADED < UNKNOWN < FAILED.

UNKNOWN hiçbir zaman NOMINAL sayılmaz; DEGRADED'den daha ağır kabul edilir
(bilinmeyen bir işlevin çalıştığına güvenilmez).

Simülasyonda modellenmeyen alanlar (ör. uçuş bilgisayarı şeritleri)
bu modele dahil EDİLMEZ; `NOT_MODELED` listesinde açıkça belirtilir,
böylece "modellenmedi" ile "sağlıklı" karıştırılmaz.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from ..core.types import HealthState, NavigationSolution

SEVERITY = {HealthState.NOMINAL: 0, HealthState.DEGRADED: 1, HealthState.UNKNOWN: 2,
            HealthState.FAILED: 3}


class Domain(str, Enum):
    ACTUATORS = "actuators"
    SENSORS = "sensors"
    NAVIGATION = "navigation"
    POWER = "power"
    COMMUNICATION = "communication"
    CONTROL = "control"


NOT_MODELED = ("computer_lanes",)


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

    def domain(self, d: Domain) -> DomainHealth:
        return next(x for x in self.domains if x.domain is d)

    def signature(self) -> tuple:
        return (self.overall,) + tuple((d.domain, d.state) for d in self.domains)

    def to_dict(self) -> dict:
        return {"overall": self.overall.value, "domains": [d.to_dict() for d in self.domains],
                "not_modeled": list(NOT_MODELED)}


def worst(states: list[HealthState]) -> HealthState:
    return max(states, key=SEVERITY.__getitem__) if states else HealthState.UNKNOWN


class VehicleHealthModel:
    def assess(self, *, actuator_states: dict[str, HealthState], hover_feasible: bool,
               airborne: bool, degraded_sensors: list[str], nav: NavigationSolution | None,
               nav_initialized: bool, energy_health: float, usable_energy_wh: float,
               energy_warning: bool, unmet_power_w: float, link_up: bool,
               controllable: bool) -> VehicleHealth:
        d = [self._actuators(actuator_states, hover_feasible, airborne),
             self._sensors(degraded_sensors),
             self._navigation(nav, nav_initialized),
             self._power(energy_health, usable_energy_wh, energy_warning, unmet_power_w),
             DomainHealth(Domain.COMMUNICATION,
                          HealthState.NOMINAL if link_up else HealthState.FAILED,
                          "c2_bagli" if link_up else "c2_yok"),
             self._control(controllable, hover_feasible)]
        return VehicleHealth(worst([x.state for x in d]), tuple(d))

    @staticmethod
    def _actuators(states: dict[str, HealthState], hover_ok: bool, airborne: bool) -> DomainHealth:
        failed = tuple(k for k, s in states.items() if s is HealthState.FAILED)
        degraded = tuple(k for k, s in states.items() if s is HealthState.DEGRADED)
        unknown = tuple(k for k, s in states.items() if s is HealthState.UNKNOWN)
        if failed and not hover_ok:
            return DomainHealth(Domain.ACTUATORS, HealthState.FAILED, "yedeklilik_yetersiz", failed)
        if unknown and airborne:
            return DomainHealth(Domain.ACTUATORS, HealthState.UNKNOWN, "gozlenmemis_eyleyici", unknown)
        if failed or degraded:
            return DomainHealth(Domain.ACTUATORS, HealthState.DEGRADED,
                                "ariza_yedeklilikle_tolere" if failed else "verim_kaybi",
                                failed + degraded)
        return DomainHealth(Domain.ACTUATORS, HealthState.NOMINAL, "nominal")

    @staticmethod
    def _sensors(degraded: list[str]) -> DomainHealth:
        if degraded:
            return DomainHealth(Domain.SENSORS, HealthState.DEGRADED, "olcum_yok_geri_donus_kaynagi",
                                tuple(sorted(degraded)))
        return DomainHealth(Domain.SENSORS, HealthState.NOMINAL, "nominal")

    @staticmethod
    def _navigation(nav: NavigationSolution | None, initialized: bool) -> DomainHealth:
        if nav is None or not initialized:
            return DomainHealth(Domain.NAVIGATION, HealthState.UNKNOWN, "cozum_yok")
        if not nav.integrity_ok:
            return DomainHealth(Domain.NAVIGATION, HealthState.FAILED, "butunluk_yok",
                                tuple(nav.sources_used))
        lost = tuple(nav.sources_rejected) + tuple(nav.sources_unavailable)
        if lost:
            return DomainHealth(Domain.NAVIGATION, HealthState.DEGRADED, "kaynak_kaybi", lost)
        return DomainHealth(Domain.NAVIGATION, HealthState.NOMINAL, "nominal")

    @staticmethod
    def _power(health: float, usable_wh: float, warning: bool, unmet_w: float) -> DomainHealth:
        if not (math.isfinite(usable_wh) and math.isfinite(health)):
            return DomainHealth(Domain.POWER, HealthState.UNKNOWN, "enerji_kestirimi_yok")
        if unmet_w > 1e-6:
            return DomainHealth(Domain.POWER, HealthState.FAILED, "guc_talebi_karsilanamiyor")
        if warning or health < 1.0:
            return DomainHealth(Domain.POWER, HealthState.DEGRADED,
                                "rezerv_uyarisi" if warning else "kaynak_bozunumu")
        return DomainHealth(Domain.POWER, HealthState.NOMINAL, "nominal")

    @staticmethod
    def _control(controllable: bool, hover_ok: bool) -> DomainHealth:
        if not controllable:
            return DomainHealth(Domain.CONTROL, HealthState.FAILED, "kontrol_kaybi")
        if not hover_ok:
            return DomainHealth(Domain.CONTROL, HealthState.DEGRADED, "aski_otoritesi_yok")
        return DomainHealth(Domain.CONTROL, HealthState.NOMINAL, "nominal")
