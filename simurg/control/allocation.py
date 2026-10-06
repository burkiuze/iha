"""Arıza toleranslı kontrol dağıtımı (control allocation).

Yöntem: eksen ağırlıklı, yeniden dağıtımlı sözde-ters (Redistributed
Pseudo-Inverse, RPI). Her iterasyonda sınır dışına çıkan eyleyiciler sınırda
sabitlenir ve kalan istek serbest eyleyicilere yeniden dağıtılır.

Sağlık vektörü h (0..1) her eyleyicinin etkinliğini ölçekler:
  h = 1   sağlam
  0<h<1   kısmi verim kaybı (ör. hasarlı pervane)
  h = 0   arızalı; eyleyici 0'da sabitlenir ve çözümden çıkarılır

Eksen ağırlıkları, istek fiziksel olarak karşılanamadığında hangi eksenden
önce feragat edileceğini belirler. Varsayılan: roll/pitch > itki > yaw.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import ArrayLike

from ..core.errors import ConfigurationError

AXES = ("Fz", "Mx", "My", "Mz")


@dataclass
class AllocationResult:
    u: np.ndarray            # eyleyici komutları
    achieved: np.ndarray     # elde edilen [Fz, Mx, My, Mz]
    error: np.ndarray        # istenen - elde edilen
    saturated: np.ndarray    # sınırda sabitlenen eyleyiciler (bool)
    feasible: bool           # istek tolerans içinde karşılandı mı


class ControlAllocator:
    def __init__(self, B: ArrayLike, lower: ArrayLike, upper: ArrayLike,
                 axis_weights: tuple[float, ...] = (10.0, 100.0, 100.0, 1.0),
                 tol: float = 1e-3) -> None:
        self.B = np.asarray(B, dtype=float)
        self.lower = np.asarray(lower, dtype=float)
        self.upper = np.asarray(upper, dtype=float)
        if self.B.shape[1] != self.lower.size or self.lower.size != self.upper.size:
            raise ConfigurationError("B sütun sayısı ile sınır vektörleri uyuşmuyor")
        self.Wv = np.diag(axis_weights)
        self.tol = tol

    def allocate(self, v_des: ArrayLike, health: ArrayLike | None = None) -> AllocationResult:
        v_des = np.asarray(v_des, dtype=float)
        n = self.B.shape[1]
        h = np.ones(n) if health is None else np.clip(np.asarray(health, float), 0.0, 1.0)
        Beff = self.B * h

        u = np.zeros(n)
        fixed = h <= 1e-6                    # arızalılar 0'da sabit
        saturated = np.zeros(n, dtype=bool)

        for _ in range(n + 1):
            idx = np.flatnonzero(~fixed)
            if idx.size == 0:
                break
            r = v_des - Beff[:, fixed] @ u[fixed]
            sol = np.linalg.pinv(self.Wv @ Beff[:, idx]) @ (self.Wv @ r)
            lo, hi = self.lower[idx], self.upper[idx]
            viol = (sol < lo - 1e-12) | (sol > hi + 1e-12)
            u[idx] = np.clip(sol, lo, hi)
            if not viol.any():
                break
            fixed[idx[viol]] = True
            saturated[idx[viol]] = True

        achieved = Beff @ u
        err = v_des - achieved
        scale = np.maximum(np.abs(v_des), 1.0)
        feasible = bool(np.all(np.abs(err) / scale < self.tol))
        return AllocationResult(u, achieved, err, saturated, feasible)

    @classmethod
    def from_regime(cls, regime: Any, tol: float = 1e-3) -> "ControlAllocator":
        """`control.effectiveness.ControlRegime` nesnesinden dağıtıcı kurar."""
        return cls(regime.B, regime.lower, regime.upper,
                   axis_weights=tuple(regime.axis_weights), tol=tol)

    def hover_margin(self, weight_n: float, health: ArrayLike | None = None) -> float:
        """Sıfır moment altında üretilebilecek azami itkinin ağırlığa oranı.

        İkili arama ile hesaplanır; > 1 ise araç hover yapabilir.
        """
        lo, hi = 0.0, float(np.sum(self.B[0].clip(min=0)))
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            if self.allocate([mid, 0, 0, 0], health).feasible:
                lo = mid
            else:
                hi = mid
        return lo / weight_n


class ScheduledAllocator:
    """Rejime bağlı etkinlik sağlayıcısıyla çalışan dağıtıcı.

    Her çağrıda sağlayıcıdan güncel B(V, σ) alınır ve RPI çözümü aynı
    `ControlAllocator` mantığıyla yapılır; böylece askı davranışı mevcut
    API ile birebir aynıdır.
    """

    def __init__(self, provider: Any, tol: float = 1e-3) -> None:
        self.provider = provider
        self.tol = tol
        self.last_regime = None

    def allocate(self, v_des: ArrayLike, health: ArrayLike | None = None,
                 conditions: Any = None) -> AllocationResult:
        regime = self.provider.regime(conditions)
        self.last_regime = regime
        return ControlAllocator.from_regime(regime, self.tol).allocate(v_des, health)
