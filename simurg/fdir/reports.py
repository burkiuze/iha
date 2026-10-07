"""Alan (domain) FDIR'leri ve standart FDIR raporu.

Sekiz alan FDIR'i (FDIR Supervisor altında) aynı biçimde rapor üretir:

    fault_detected        arıza tespit edildi mi
    fault_isolated        yalıtılan bileşenler
    fault_class           arıza sınıfı (FaultClass)
    confidence            0..1, kararın güveni (gözlenmeyen -> 0)
    health_state          NOMINAL / DEGRADED / FAILED / UNKNOWN
    recommended_degradation  önerilen bozulmuş çalışma biçimi (yalnızca ÖNERİ;
                          mod değişimi yalnızca Flight Mode Machine'den geçer)

Raporlar Vehicle Health Manager'da birleştirilir. Fail-safe: gözlenmeyen /
bilgisi olmayan alan UNKNOWN raporlar; asla NOMINAL varsayılmaz.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..core.types import HealthState, NavigationSolution
from .lanes import EXCLUDED, LaneState


class FdirDomain(str, Enum):
    SENSOR = "sensor"
    NAVIGATION = "navigation"
    FCC = "fcc"
    MOTOR = "motor"
    ACTUATOR = "actuator"
    ENERGY = "energy"
    COMMUNICATION = "communication"
    MISSION_COMPUTER = "mission_computer"


class FaultClass(str, Enum):
    NONE = "none"
    UNOBSERVED = "unobserved"
    SENSOR_LOSS = "sensor_loss"
    SENSOR_DEGRADATION = "sensor_degradation"
    NAV_SOURCE_LOSS = "nav_source_loss"
    NAV_INTEGRITY_LOSS = "nav_integrity_loss"
    LANE_DIVERGENCE = "lane_divergence"
    LANE_LOSS = "lane_loss"
    MOTOR_DEGRADATION = "motor_degradation"
    MOTOR_LOSS = "motor_loss"
    ACTUATOR_LOSS = "actuator_loss"
    ENERGY_DEGRADATION = "energy_degradation"
    POWER_SHORTFALL = "power_shortfall"
    LINK_LOSS = "link_loss"
    PROPOSAL_INVALID = "proposal_invalid"


@dataclass(frozen=True)
class FdirReport:
    domain: FdirDomain
    fault_detected: bool
    fault_isolated: tuple[str, ...]
    fault_class: FaultClass
    confidence: float
    health_state: HealthState
    recommended_degradation: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"domain": self.domain.value, "fault_detected": self.fault_detected,
                "fault_isolated": list(self.fault_isolated),
                "fault_class": self.fault_class.value, "confidence": round(self.confidence, 4),
                "health_state": self.health_state.value,
                "recommended_degradation": self.recommended_degradation, "reason": self.reason}


def _ok(d: FdirDomain, reason: str = "nominal") -> FdirReport:
    return FdirReport(d, False, (), FaultClass.NONE, 1.0, HealthState.NOMINAL, "yok", reason)


def _unknown(d: FdirDomain, reason: str, comps: tuple[str, ...] = ()) -> FdirReport:
    return FdirReport(d, False, comps, FaultClass.UNOBSERVED, 0.0, HealthState.UNKNOWN,
                      "bilinmeyen_saglikli_sayilmaz", reason)


# Ölçümü olmadığında açık geri dönüş kaynağı OLMAYAN sensörler.
NO_FALLBACK_SENSORS = frozenset({"RPM"})


def sensor_fdir(states: dict[str, HealthState], airborne: bool) -> FdirReport:
    d = FdirDomain.SENSOR
    failed = tuple(k for k, s in sorted(states.items()) if s is HealthState.FAILED)
    degraded = tuple(k for k, s in sorted(states.items()) if s is HealthState.DEGRADED)
    unknown = tuple(k for k, s in sorted(states.items()) if s is HealthState.UNKNOWN)
    critical = tuple(k for k in failed if k in NO_FALLBACK_SENSORS)
    if critical:
        return FdirReport(d, True, critical, FaultClass.SENSOR_LOSS, 1.0, HealthState.FAILED,
                          "motor_fdir_kor_acil_inis_degerlendir", "geri_donussuz_sensor_kaybi")
    if failed:
        return FdirReport(d, True, failed, FaultClass.SENSOR_LOSS, 1.0, HealthState.DEGRADED,
                          "geri_donus_kaynagi_kullan", "sensor_kaybi_yedekli")
    if degraded:
        return FdirReport(d, True, degraded, FaultClass.SENSOR_DEGRADATION, 0.6,
                          HealthState.DEGRADED, "olcum_agirligini_dusur", "gecersiz_ya_da_akla_yatkin_degil")
    if unknown and airborne:
        return _unknown(d, "olcumu_olmayan_sensor", unknown)
    return _ok(d)


def legacy_sensor_fdir(degraded: list[str]) -> FdirReport:
    """Eski giriş biçimi: yalnızca bozulmuş hava verisi sensörleri listesi."""
    if degraded:
        return FdirReport(FdirDomain.SENSOR, True, tuple(sorted(degraded)),
                          FaultClass.SENSOR_LOSS, 1.0, HealthState.DEGRADED,
                          "geri_donus_kaynagi_kullan", "olcum_yok_geri_donus_kaynagi")
    return _ok(FdirDomain.SENSOR)


def navigation_fdir(nav: NavigationSolution | None, initialized: bool) -> FdirReport:
    d = FdirDomain.NAVIGATION
    if nav is None or not initialized:
        return _unknown(d, "cozum_yok")
    if not nav.integrity_ok:
        return FdirReport(d, True, tuple(nav.sources_rejected) + tuple(nav.sources_unavailable),
                          FaultClass.NAV_INTEGRITY_LOSS, 1.0, HealthState.FAILED,
                          "loiter_hold_ataletsel_tutma", "butunluk_yok")
    lost = tuple(nav.sources_rejected) + tuple(nav.sources_unavailable)
    if lost:
        return FdirReport(d, True, lost, FaultClass.NAV_SOURCE_LOSS,
                          float(min(max(nav.confidence, 0.0), 1.0)), HealthState.DEGRADED,
                          "kalan_kaynaklarla_devam", "kaynak_kaybi")
    return _ok(d)


def fcc_fdir(lanes: dict[str, LaneState] | None) -> FdirReport:
    d = FdirDomain.FCC
    if lanes is None:
        return _unknown(d, "serit_bilgisi_yok")
    out = tuple(l for l, s in sorted(lanes.items()) if s in EXCLUDED)
    avail = [l for l, s in lanes.items() if s not in EXCLUDED]
    cls = (FaultClass.LANE_LOSS if any(lanes[l] is LaneState.FAILED for l in out)
           else FaultClass.LANE_DIVERGENCE)
    if not avail:
        return FdirReport(d, True, out, FaultClass.LANE_LOSS, 1.0, HealthState.FAILED,
                          "parasut", "serit_yok")
    if len(avail) == 1:
        return FdirReport(d, True, out, cls, 1.0, HealthState.FAILED,
                          "acil_inis_yedeksiz_serit", "tekli_mod_yedeksiz")
    if out:
        return FdirReport(d, True, out, cls, 1.0, HealthState.DEGRADED,
                          "ikili_mod_devam", "serit_yalitildi")
    if any(lanes[l] is LaneState.UNKNOWN for l in avail):
        return _unknown(d, "serit_cikti_yok", tuple(l for l in avail if lanes[l] is LaneState.UNKNOWN))
    deg = tuple(l for l in avail if lanes[l] is LaneState.DEGRADED)
    if deg:
        return FdirReport(d, True, deg, FaultClass.LANE_DIVERGENCE, 0.5, HealthState.DEGRADED,
                          "izlemeye_devam", "serit_gozlem_altinda")
    return _ok(d)


def motor_fdir(states: dict[str, HealthState], hover_ok: bool, airborne: bool) -> FdirReport:
    d = FdirDomain.MOTOR
    failed = tuple(k for k, s in states.items() if s is HealthState.FAILED)
    degraded = tuple(k for k, s in states.items() if s is HealthState.DEGRADED)
    unknown = tuple(k for k, s in states.items() if s is HealthState.UNKNOWN)
    if failed and not hover_ok:
        return FdirReport(d, True, failed, FaultClass.MOTOR_LOSS, 1.0, HealthState.FAILED,
                          "dagitimdan_cikar_acil_inis", "yedeklilik_yetersiz")
    if unknown and airborne:
        return _unknown(d, "gozlenmemis_eyleyici", unknown)
    if failed:
        return FdirReport(d, True, failed, FaultClass.MOTOR_LOSS, 1.0, HealthState.DEGRADED,
                          "dagitimdan_cikar", "ariza_yedeklilikle_tolere")
    if degraded:
        return FdirReport(d, True, degraded, FaultClass.MOTOR_DEGRADATION, 0.7,
                          HealthState.DEGRADED, "verim_agirlikli_dagitim", "verim_kaybi")
    return _ok(d)


def actuator_fdir(states: dict[str, HealthState]) -> FdirReport:
    d = FdirDomain.ACTUATOR
    failed = tuple(k for k, s in states.items() if s is HealthState.FAILED)
    degraded = tuple(k for k, s in states.items() if s is HealthState.DEGRADED)
    if states and len(failed) == len(states):
        return FdirReport(d, True, failed, FaultClass.ACTUATOR_LOSS, 1.0, HealthState.FAILED,
                          "itki_diferansiyeli_ile_kontrol", "tum_yuzeyler_kayip")
    if failed:
        return FdirReport(d, True, failed, FaultClass.ACTUATOR_LOSS, 1.0, HealthState.DEGRADED,
                          "dagitimdan_cikar", "yuzey_kaybi_yedekli")
    if degraded:
        return FdirReport(d, True, degraded, FaultClass.ACTUATOR_LOSS, 0.6, HealthState.DEGRADED,
                          "dagitimdan_cikar", "yuzey_bozulmasi")
    return _ok(d)


def energy_fdir(health: float, usable_wh: float, warning: bool, unmet_w: float) -> FdirReport:
    d = FdirDomain.ENERGY
    if not (math.isfinite(usable_wh) and math.isfinite(health)):
        return _unknown(d, "enerji_kestirimi_yok")
    if unmet_w > 1e-6:
        return FdirReport(d, True, ("power_bus",), FaultClass.POWER_SHORTFALL, 1.0,
                          HealthState.FAILED, "guc_talebini_azalt_acil_inis_degerlendir",
                          "guc_talebi_karsilanamiyor")
    if warning:
        return FdirReport(d, True, ("reserve",), FaultClass.ENERGY_DEGRADATION, 1.0,
                          HealthState.DEGRADED, "eve_donus", "rezerv_uyarisi")
    if health < 1.0:
        return FdirReport(d, True, ("sources",), FaultClass.ENERGY_DEGRADATION,
                          1.0 - health, HealthState.DEGRADED, "guc_butcesini_dusur", "kaynak_bozunumu")
    return _ok(d)


def communication_fdir(link_up: bool) -> FdirReport:
    if link_up:
        return _ok(FdirDomain.COMMUNICATION, "c2_bagli")
    return FdirReport(FdirDomain.COMMUNICATION, True, ("link:c2",), FaultClass.LINK_LOSS, 1.0,
                      HealthState.FAILED, "baglanti_kaybi_zamanlayicisi_eve_donus", "c2_yok")


MISSION_FAIL_AFTER_S = 3.0


def mission_computer_fdir(proposal_ok: bool | None, rejected_for_s: float) -> FdirReport:
    """Görev bilgisayarı sağlığı, ÖNERİ akışının geçerliliğinden gözlenir.

    proposal_ok=None: öneri akışı gözlenmedi (UNKNOWN). Öneri gerekmeyen
    modlarda çağıran taraf görev yöneticisinin çalıştığını (kalp atışı)
    True olarak bildirir.
    """
    d = FdirDomain.MISSION_COMPUTER
    if proposal_ok is None:
        return _unknown(d, "oneri_akisi_gozlenmedi")
    if proposal_ok:
        return _ok(d)
    if rejected_for_s >= MISSION_FAIL_AFTER_S:
        return FdirReport(d, True, ("mission_computer",), FaultClass.PROPOSAL_INVALID, 1.0,
                          HealthState.FAILED, "guvenlik_kontrolcusu_yetkili", "kalici_gecersiz_oneri")
    return FdirReport(d, True, ("mission_computer",), FaultClass.PROPOSAL_INVALID, 0.5,
                      HealthState.DEGRADED, "guvenlik_kontrolcusu_yetkili", "gecersiz_oneri")
