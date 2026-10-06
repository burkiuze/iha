"""Enerji rezerv izleyicisi: eve dönüş için gereken enerji ve uyarı histerezisi.

    gerekli = (P_seyir * mesafe / yer_hızı + E_iniş) * pay
    uyarı   : kullanılabilir < faktör * gerekli
    temizle : kullanılabilir > faktör * gerekli * 1.1

Fail-safe: kullanılabilir enerji kestirimi sonlu değilse (bilinmiyor) uyarı
verilir; bilinmeyen enerji yeterli kabul edilmez.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

LANDING_ENERGY_WH = 60.0
RETURN_MARGIN = 1.3
CLEAR_HYSTERESIS = 1.1


@dataclass(frozen=True)
class ReserveAssessment:
    usable_wh: float
    required_wh: float
    warning_factor: float
    warn_now: bool          # bu değerlendirmede uyarı başladı
    warning_active: bool

    def to_dict(self) -> dict:
        finite = math.isfinite(self.usable_wh)
        return {"usable_wh": round(self.usable_wh, 3) if finite else None,
                "required_wh": round(self.required_wh, 3),
                "warning_factor": self.warning_factor,
                "reason": ("enerji_kestirimi_yok" if not finite
                           else "kullanilabilir_enerji<faktor*gerekli")}


def required_return_energy_wh(distance_m: float, groundspeed_mps: float,
                              cruise_power_w: float) -> float:
    return (cruise_power_w * distance_m / max(groundspeed_mps, 1e-3) / 3600.0
            + LANDING_ENERGY_WH) * RETURN_MARGIN


class ReserveMonitor:
    def __init__(self, warning_factor: float) -> None:
        self.factor = warning_factor
        self.active = False

    def assess(self, usable_wh: float, distance_m: float, groundspeed_mps: float,
               cruise_power_w: float) -> ReserveAssessment:
        need = required_return_energy_wh(distance_m, groundspeed_mps, cruise_power_w)
        low = (not math.isfinite(usable_wh)) or usable_wh < self.factor * need
        warn_now = False
        if not self.active and low:
            self.active = warn_now = True
        elif self.active and math.isfinite(usable_wh) and \
                usable_wh > self.factor * need * CLEAR_HYSTERESIS:
            self.active = False
        return ReserveAssessment(usable_wh, need, self.factor, warn_now, self.active)
