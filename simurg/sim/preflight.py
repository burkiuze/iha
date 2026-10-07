"""Uçuş öncesi denetçi (Preflight Supervisor).

Sekiz kontrolün TAMAMI geçmeden `preflight_ok` doğru olmaz; mod makinesinin
`PREFLIGHT -> ARMED` koruması bunu gerektirdiği için araç silahlanamaz.

Kontroller simülasyon durumunu yalnızca OKUR (sensör ölçümü almaz, RNG
tüketmez); böylece determinizm ve mevcut senaryo sonuçları etkilenmez.
Bu bir yazılım denetimidir; gerçek uçuş öncesi prosedür değildir.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from ..core.config import SafetyConfig
from ..power.reserve import LANDING_ENERGY_WH, RETURN_MARGIN
from ..safety.rta import Envelope

CHECK_NAMES = ("configuration", "sensor_health", "navigation", "energy",
               "control_availability", "communication", "mission_validation",
               "safety_configuration")


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    passed: bool
    reason: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "reason": self.reason,
                "details": self.details}


@dataclass(frozen=True)
class PreflightReport:
    checks: tuple[PreflightCheck, ...]

    @property
    def passed(self) -> bool:
        return len(self.checks) == len(CHECK_NAMES) and all(c.passed for c in self.checks)

    @property
    def failed(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.checks if not c.passed)

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "failed_checks": list(self.failed),
                "checks": [c.to_dict() for c in self.checks]}


@dataclass(frozen=True)
class PreflightInputs:
    sensor_status: dict[str, bool]          # sensör kimliği -> kullanılabilir mi
    nav_sources: tuple[str, ...]            # konum kaynağı kimlikleri
    min_nav_sources: int
    usable_energy_wh: float
    mission_distance_m: float
    cruise_speed_mps: float
    cruise_power_w: float
    hover_margin: float
    failed_actuators: tuple[str, ...]
    link_up: bool
    waypoints: tuple[tuple[float, float], ...]
    home_ne: tuple[float, float]
    takeoff_alt_m: float
    safety: SafetyConfig
    soft: Envelope
    hard: Envelope


class PreflightSupervisor:
    REQUIRED_SENSORS = ("BARO", "AIRSPEED", "RPM")

    def run(self, i: PreflightInputs) -> PreflightReport:
        return PreflightReport((
            self._configuration(), self._sensors(i), self._navigation(i), self._energy(i),
            self._control(i), self._communication(i), self._mission(i), self._safety(i)))

    @staticmethod
    def _configuration() -> PreflightCheck:
        # Yapılandırma nesneleri kurulurken doğrulanır (ConfigurationError);
        # buraya ulaşıldıysa araç/simülasyon yapılandırması geçerlidir.
        return PreflightCheck("configuration", True, "dogrulandi")

    def _sensors(self, i: PreflightInputs) -> PreflightCheck:
        missing = [s for s in self.REQUIRED_SENSORS if not i.sensor_status.get(s, False)]
        return PreflightCheck("sensor_health", not missing,
                              "kritik_sensor_yok" if missing else "tum_kritik_sensorler_hazir",
                              {"unavailable": missing})

    @staticmethod
    def _navigation(i: PreflightInputs) -> PreflightCheck:
        avail = [s for s in i.nav_sources if i.sensor_status.get(s, False)]
        ok = len(avail) >= i.min_nav_sources
        return PreflightCheck("navigation", ok,
                              "yeterli_bagimsiz_kaynak" if ok else "butunluk_icin_kaynak_yetersiz",
                              {"available": avail, "required": i.min_nav_sources})

    @staticmethod
    def _energy(i: PreflightInputs) -> PreflightCheck:
        cruise_wh = i.cruise_power_w * i.mission_distance_m / max(i.cruise_speed_mps, 1e-3) / 3600.0
        need = (cruise_wh + 2.0 * LANDING_ENERGY_WH) * RETURN_MARGIN    # kalkış + iniş
        ok = math.isfinite(i.usable_energy_wh) and i.usable_energy_wh >= need
        return PreflightCheck("energy", ok, "gorev_enerjisi_yeterli" if ok else "gorev_enerjisi_yetersiz",
                              {"usable_wh": round(i.usable_energy_wh, 3)
                               if math.isfinite(i.usable_energy_wh) else None,
                               "required_wh": round(need, 3)})

    @staticmethod
    def _control(i: PreflightInputs) -> PreflightCheck:
        ok = i.hover_margin > i.safety.hover_margin_min and not i.failed_actuators
        return PreflightCheck("control_availability", ok,
                              "kontrol_otoritesi_var" if ok else "kontrol_otoritesi_yetersiz",
                              {"hover_margin": round(i.hover_margin, 4),
                               "failed_actuators": list(i.failed_actuators)})

    @staticmethod
    def _communication(i: PreflightInputs) -> PreflightCheck:
        return PreflightCheck("communication", i.link_up, "c2_bagli" if i.link_up else "c2_yok")

    @staticmethod
    def _mission(i: PreflightInputs) -> PreflightCheck:
        r = i.safety.geofence_radius_m
        outside = [list(w) for w in i.waypoints
                   if math.hypot(w[0] - i.home_ne[0], w[1] - i.home_ne[1]) > r - 100.0]
        problems = (["ara_nokta_geofence_disi"] if outside else []) + \
            (["ara_nokta_yok"] if not i.waypoints else []) + \
            (["kalkis_irtifasi_dusuk"] if i.takeoff_alt_m < 40.0 else [])
        return PreflightCheck("mission_validation", not problems,
                              ",".join(problems) or "gorev_gecerli", {"outside_fence": outside})

    @staticmethod
    def _safety(i: PreflightInputs) -> PreflightCheck:
        s, so, h = i.safety, i.soft, i.hard
        problems = []
        if not (so.min_alt_m > h.min_alt_m and so.min_fence_dist_m > h.min_fence_dist_m
                and so.min_airspeed_mps > h.min_airspeed_mps
                and so.max_airspeed_mps < h.max_airspeed_mps
                and so.max_bank_deg < h.max_bank_deg and so.max_pitch_deg < h.max_pitch_deg):
            problems.append("yumusak_zarf_sert_zarfin_icinde_degil")
        if s.hover_margin_min < 1.0:
            problems.append("hover_marji_esigi_1_altinda")
        if s.geofence_radius_m <= 0 or s.link_loss_rth_s <= 0 or s.rta_horizon_s <= 0:
            problems.append("pozitif_olmayan_guvenlik_parametresi")
        return PreflightCheck("safety_configuration", not problems,
                              ",".join(problems) or "guvenlik_yapilandirmasi_tutarli")
