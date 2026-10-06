"""Uçuş rejimine bağlı kontrol etkinliği: B(V, σ).

Tahsis her zaman askı (hover) tahsis çerçevesinde yapılır (bkz.
`simurg/config.py`): satırlar [Fz_h, Mx_h, My_h, Mz_h]. Gövde çerçevesine
eşleme `simurg.core.frames` başlığında: Fz_h = itki (b_x boyunca),
Mx_h = -M_z,gövde, My_h = M_y,gövde, Mz_h = M_x,gövde.

Rejimler
  * askı (σ=0)   : mevcut `hover_effectiveness()` ile birebir aynı.
  * geçiş        : itki hız ile azalır; elevonlar pervane akımı + dinamik
                   basınçla etkinleşir; eksen ağırlıkları σ ile harmanlanır.
  * seyir (σ=1)  : iç (katlanır) motorların üst sınırı 0'dır.

σ = sat((V - 5) / 15, 0, 1)  (docs/06-ucus-kontrol.md §6)

Kazançlar ve katsayılar araştırma amaçlı yer tutuculardır.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from .. import config as legacy
from ..core.config import VehicleConfig

HOVER_AXIS_WEIGHTS = np.array([10.0, 100.0, 100.0, 1.0])    # yaw_h en önce feda
CRUISE_AXIS_WEIGHTS = np.array([10.0, 10.0, 100.0, 100.0])  # roll_b (Mz_h) korunur


def blend_sigma(airspeed_mps: float, v0: float = 5.0, span: float = 15.0) -> float:
    return float(np.clip((airspeed_mps - v0) / span, 0.0, 1.0))


@dataclass(frozen=True)
class ControlRegime:
    name: str
    B: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    axis_weights: np.ndarray
    sigma: float


@dataclass(frozen=True)
class EffectivenessConditions:
    airspeed_mps: float = 0.0
    density: float = legacy.RHO_SL
    sigma: float | None = None          # None -> hava hızından hesaplanır
    thrust_scale: float = 1.0           # pervane itki düşümü (V ile)
    wash_force_n: float | None = None   # None -> yapılandırmadaki askı değeri
    fold_inner_motors: bool = False


class EffectivenessProvider(Protocol):
    def regime(self, cond: EffectivenessConditions) -> ControlRegime: ...


class HoverEffectiveness:
    """Mevcut statik askı modelini sağlayıcı arayüzüne sarar."""

    def __init__(self) -> None:
        B, lo, hi = legacy.hover_effectiveness()
        self._r = ControlRegime("hover", B, lo, hi, HOVER_AXIS_WEIGHTS.copy(), 0.0)

    def regime(self, cond: EffectivenessConditions | None = None) -> ControlRegime:
        return self._r


class ScheduledEffectiveness:
    """Hız ve geçiş ilerlemesine göre harmanlanan etkinlik modeli."""

    def __init__(self, vehicle: VehicleConfig | None = None) -> None:
        self.v = vehicle or VehicleConfig()

    def regime(self, cond: EffectivenessConditions) -> ControlRegime:
        v = self.v
        sigma = blend_sigma(cond.airspeed_mps) if cond.sigma is None else float(cond.sigma)
        q = 0.5 * cond.density * cond.airspeed_mps ** 2
        wash = v.prop_wash_force_n if cond.wash_force_n is None else cond.wash_force_n
        f_el = wash + q * v.elevon_area_m2 * v.elevon_cl_delta_per_rad * v.elevon_max_deflection_rad
        cols, lo, hi = [], [], []
        for m in v.motors:
            folded = cond.fold_inner_motors and m.folding
            t = 0.0 if folded else m.max_thrust * cond.thrust_scale   # katlı: etkisiz
            cols.append([t, m.y * t, -m.x * t, v.torque_coeff_m * m.spin * t])
            lo.append(0.0)
            hi.append(0.0 if folded else 1.0)
        for s in v.surfaces:
            # kuvvet -b_z (= +h_x) yönünde, (x_e, y) noktasında:
            # M_b = (-y F, x_e F, 0) -> My_h = x_e F, Mz_h = -y F
            cols.append([0.0, 0.0, v.elevon_x_m * f_el, -s.y * f_el])
            lo.append(-1.0)
            hi.append(1.0)
        w = (1 - sigma) * HOVER_AXIS_WEIGHTS + sigma * CRUISE_AXIS_WEIGHTS
        name = "hover" if sigma <= 0 else ("cruise" if sigma >= 1 else "transition")
        return ControlRegime(name, np.array(cols).T, np.array(lo), np.array(hi), w, sigma)


def body_to_alloc(thrust_n: float, moment_body: np.ndarray) -> np.ndarray:
    """Gövde isteği -> tahsis çerçevesi [Fz_h, Mx_h, My_h, Mz_h]."""
    mx, my, mz = moment_body
    return np.array([thrust_n, -mz, my, mx])


def alloc_to_body(v_alloc: np.ndarray) -> tuple[float, np.ndarray]:
    fz, mxh, myh, mzh = v_alloc
    return float(fz), np.array([mzh, myh, -mxh])
