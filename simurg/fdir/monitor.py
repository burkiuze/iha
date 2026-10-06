"""Arıza tespit, yalıtım ve yeniden yapılandırma (FDIR) yapı taşları.

* MotorHealthMonitor : komut-tepki artığı üzerinde CUSUM ile motor/pervane
  verim kaybı tespiti; kontrol dağıtıcısına sağlık vektörü üretir. Tespit
  (CUSUM) ile şiddet kestirimi (verim EMA'sı) ayrıdır: sabit bir kısmi
  hasar DEGRADED olarak kalır, zamanla FAILED'a tırmanmaz.
* TripleLaneVoter    : üç bağımsız (farklı donanım/yazılım) şeritten gelen
  ölçümlerde orta değer seçimi ve kalıcı uyuşmazlığa dayalı şerit yalıtımı.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np


class Health(Enum):
    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass
class MotorHealthMonitor:
    n: int = 8
    drift: float = 0.03          # normal model hatası toleransı (%3)
    h_degraded: float = 0.5      # CUSUM eşiği: tespit
    g_max: float = 5.0           # CUSUM üst sınırı (kalıcı arızada şişmesin)
    eff_failed: float = 0.30     # tahmini itki verimi bunun altında -> arızalı
    dead_ratio: float = 0.15     # komut > %30 iken devir < %15 -> anında arıza
    ema_alpha: float = 0.05

    def __post_init__(self):
        self.g = np.zeros(self.n)
        self.eff = np.ones(self.n)       # tahmini verim (sağlık)
        self.state = [Health.OK] * self.n

    def update(self, rpm_cmd, rpm_meas) -> np.ndarray:
        rpm_cmd = np.asarray(rpm_cmd, float)
        rpm_meas = np.asarray(rpm_meas, float)
        for i in range(self.n):
            if self.state[i] is Health.FAILED:
                continue
            c = max(rpm_cmd[i], 1.0)
            ratio = rpm_meas[i] / c
            if rpm_cmd[i] > 0.3 * self._ref(rpm_cmd) and ratio < self.dead_ratio:
                self._fail(i)
                continue
            r = 1.0 - ratio
            self.g[i] = min(max(0.0, self.g[i] + abs(r) - self.drift), self.g_max)
            # itki ~ devir^2
            self.eff[i] += self.ema_alpha * (min(ratio, 1.0) ** 2 - self.eff[i])
            if self.eff[i] < self.eff_failed:
                self._fail(i)
            elif self.g[i] > self.h_degraded:
                self.state[i] = Health.DEGRADED
        return self.health()

    @staticmethod
    def _ref(rpm_cmd) -> float:
        return float(np.max(rpm_cmd)) if np.max(rpm_cmd) > 0 else 1.0

    def _fail(self, i: int):
        self.state[i] = Health.FAILED
        self.eff[i] = 0.0

    def health(self) -> np.ndarray:
        h = np.ones(self.n)
        for i, s in enumerate(self.state):
            if s is Health.FAILED:
                h[i] = 0.0
            elif s is Health.DEGRADED:
                h[i] = float(np.clip(self.eff[i], 0.05, 1.0))
        return h


@dataclass
class TripleLaneVoter:
    tol: float
    persistence: int = 5                  # ardışık uyuşmazlık sayısı
    isolated: list[bool] = field(default_factory=lambda: [False, False, False])

    def __post_init__(self):
        self._miss = [0, 0, 0]

    def vote(self, a, b, c) -> np.ndarray:
        lanes = [np.atleast_1d(np.asarray(x, float)) for x in (a, b, c)]
        active = [i for i in range(3) if not self.isolated[i]]
        if not active:
            raise RuntimeError("tüm şeritler yalıtıldı")
        stack = np.array([lanes[i] for i in active])
        if len(active) == 3:
            out = np.median(stack, axis=0)
        else:
            out = np.mean(stack, axis=0)  # ikili: ortalama + karşılaştırma
        if len(active) == 3:
            for i in active:
                if np.max(np.abs(lanes[i] - out)) > self.tol:
                    self._miss[i] += 1
                    if self._miss[i] >= self.persistence:
                        self.isolated[i] = True
                else:
                    self._miss[i] = 0
        return out

    def disagree(self, a, b, c) -> bool:
        """İki şerit kaldığında aralarındaki fark tolerans dışı mı?"""
        lanes = [np.atleast_1d(np.asarray(x, float)) for x in (a, b, c)]
        active = [lanes[i] for i in range(3) if not self.isolated[i]]
        if len(active) != 2:
            return False
        return bool(np.max(np.abs(active[0] - active[1])) > self.tol)
