"""Sistem denetçisi (System Supervisor): üst seviye sistem durumu.

Doğrudan hiçbir eyleyiciyi sürmez ve mod değiştirmez; uçuş modu, araç
sağlığı, navigasyon, enerji, RTA ve haberleşme bilgisini birleştirip
operatöre/kayda tek bir durum verir:

  EMERGENCY   : acil iniş/paraşüt modu, kontrol kaybı ya da araç sağlığı CRITICAL
  CONTINGENCY : acil durum kuralıyla girilmiş mod, RTA kilidi,
                nav bütünlüğü ya da C2 kaybı, araç sağlığı CONTINGENCY
  DEGRADED    : araç sağlığı NOMINAL değil (UNKNOWN dahil), RTA güvenlik
                kaynağında, enerji uyarısı ya da geçersiz YZ önerisi

Girdiler: araç sağlığı (FDIR raporları, nav bütünlüğü, enerji, haberleşme,
kontrol otoritesi, FCC şeritleri dahil), RTA durumu, uçuş modu.
  NORMAL      : yukarıdakilerin hiçbiri

Kurallar yukarıdan aşağı değerlendirilir; ilk eşleşen durum seçilir ve
eşleşen tüm gerekçeler kaydedilir.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..core.types import HealthState
from ..fdir.vehicle_health import Domain, VehicleHealth, VehicleHealthLevel
from ..modes.flight_modes import Mode


class SystemState(str, Enum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    CONTINGENCY = "contingency"
    EMERGENCY = "emergency"


SYSTEM_SEVERITY = {SystemState.NORMAL: 0, SystemState.DEGRADED: 1,
                   SystemState.CONTINGENCY: 2, SystemState.EMERGENCY: 3}


@dataclass(frozen=True)
class SystemAssessment:
    state: SystemState
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return {"state": self.state.value, "reasons": list(self.reasons),
                "reason": ",".join(self.reasons) or "nominal"}


class SystemSupervisor:
    def assess(self, *, mode: Mode, health: VehicleHealth, rta_on_safety: bool,
               rta_latched: bool, contingency_mode: bool, energy_warning: bool,
               proposal_rejected: bool) -> SystemAssessment:
        emergency = []
        if mode in (Mode.EMERGENCY_LAND, Mode.PARACHUTE):
            emergency.append(f"mod:{mode.name}")
        if health.domain(Domain.CONTROL).state is HealthState.FAILED:
            emergency.append("kontrol_kaybi")
        if health.level is VehicleHealthLevel.CRITICAL:
            emergency.append("arac_sagligi_kritik")
        if emergency:
            return SystemAssessment(SystemState.EMERGENCY, tuple(emergency))

        cont = []
        if contingency_mode:
            cont.append(f"acil_durum_modu:{mode.name}")
        if rta_latched:
            cont.append("rta_kilitli")
        if health.domain(Domain.NAVIGATION).state is HealthState.FAILED:
            cont.append("nav_butunluk_kaybi")
        if health.domain(Domain.COMMUNICATION).state is HealthState.FAILED:
            cont.append("c2_kaybi")
        if health.level is VehicleHealthLevel.CONTINGENCY:
            cont += [f"saglik:{r}" for r in health.reasons if ":failed:" in r]
        if cont:
            return SystemAssessment(SystemState.CONTINGENCY, tuple(cont))

        deg = [f"saglik:{d.domain.value}:{d.state.value}" for d in health.domains
               if d.state is not HealthState.NOMINAL]
        if rta_on_safety:
            deg.append("rta_guvenlik_kaynaginda")
        if energy_warning:
            deg.append("enerji_uyarisi")
        if proposal_rejected:
            deg.append("gecersiz_yz_onerisi")
        if deg:
            return SystemAssessment(SystemState.DEGRADED, tuple(deg))
        return SystemAssessment(SystemState.NORMAL, ())
