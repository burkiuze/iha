"""Arıza tespit, yalıtım ve yeniden yapılandırma (FDIR) yapı taşları.

* MotorHealthMonitor : komut-tepki artığı üzerinde CUSUM ile motor/pervane
  verim kaybı tespiti; kontrol dağıtıcısına sağlık vektörü üretir. Tespit
  (CUSUM) ile şiddet kestirimi (verim EMA'sı) ayrıdır: sabit bir kısmi
  hasar DEGRADED olarak kalır, zamanla FAILED'a tırmanmaz.
* SurfaceMonitor     : kontrol yüzeyi komut-konum artığıyla takılı/devre dışı
  yüzey tespiti.
* TripleLaneVoter    : üç bağımsız (farklı donanım/yazılım) şeritten gelen
  ölçümlerde orta değer seçimi ve kalıcı uyuşmazlığa dayalı şerit yalıtımı.

Tüm izleyiciler `reports()` ile ortak `core.types.ComponentHealth`
biçiminde rapor üretir (NOMINAL / DEGRADED / FAILED / UNKNOWN).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from ..core.types import ComponentHealth, HealthState


class Health(Enum):
    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"


_TO_STATE = {Health.OK: HealthState.NOMINAL, Health.DEGRADED: HealthState.DEGRADED,
             Health.FAILED: HealthState.FAILED}


def to_health_state(h: Health) -> HealthState:
    return _TO_STATE[h]


@dataclass
class MotorHealthMonitor:
    n: int = 8
    drift: float = 0.03          # normal model hatası toleransı (%3)
    h_degraded: float = 0.5      # CUSUM eşiği: tespit
    g_max: float = 5.0           # CUSUM üst sınırı (kalıcı arızada şişmesin)
    eff_failed: float = 0.30     # tahmini itki verimi bunun altında -> arızalı
    dead_ratio: float = 0.15     # komut > %30 iken devir < %15 -> anında arıza
    ema_alpha: float = 0.05
    min_observable: float = 0.05  # komut < bu x maks komut -> gözlenemez, güncelleme yok
    min_observable_abs: float = 0.0  # mutlak devir alt sınırı (düşük devirde gürültü baskın)

    def __post_init__(self):
        self.g = np.zeros(self.n)
        self.eff = np.ones(self.n)       # tahmini verim (sağlık)
        self.state = [Health.OK] * self.n
        self.reason = [""] * self.n
        self.observed = np.zeros(self.n, dtype=bool)

    def update(self, rpm_cmd: np.ndarray, rpm_meas: np.ndarray) -> np.ndarray:
        rpm_cmd = np.asarray(rpm_cmd, float)
        rpm_meas = np.asarray(rpm_meas, float)
        ref = self._ref(rpm_cmd)
        for i in range(self.n):
            if self.state[i] is Health.FAILED:
                continue
            if rpm_cmd[i] < max(self.min_observable * ref, self.min_observable_abs):
                continue        # durdurulmuş (ör. katlanmış iç pervane): bilgi yok
            self.observed[i] = True
            c = max(rpm_cmd[i], 1.0)
            ratio = rpm_meas[i] / c
            if rpm_cmd[i] > 0.3 * ref and ratio < self.dead_ratio:
                self._fail(i, "devir_yok")
                continue
            r = 1.0 - ratio
            self.g[i] = min(max(0.0, self.g[i] + abs(r) - self.drift), self.g_max)
            # itki ~ devir^2
            self.eff[i] += self.ema_alpha * (min(ratio, 1.0) ** 2 - self.eff[i])
            if self.eff[i] < self.eff_failed:
                self._fail(i, "verim_esik_alti")
            elif self.g[i] > self.h_degraded:
                self.state[i] = Health.DEGRADED
                self.reason[i] = "cusum_devir_artigi"
        return self.health()

    @staticmethod
    def _ref(rpm_cmd) -> float:
        return float(np.max(rpm_cmd)) if np.max(rpm_cmd) > 0 else 1.0

    def _fail(self, i: int, reason: str = ""):
        self.state[i] = Health.FAILED
        self.eff[i] = 0.0
        self.reason[i] = reason

    def health(self) -> np.ndarray:
        h = np.ones(self.n)
        for i, s in enumerate(self.state):
            if s is Health.FAILED:
                h[i] = 0.0
            elif s is Health.DEGRADED:
                h[i] = float(np.clip(self.eff[i], 0.05, 1.0))
        return h

    def reports(self, timestamp: float, ids: list[str] | None = None) -> list[ComponentHealth]:
        ids = ids or [f"motor{i}" for i in range(self.n)]
        h = self.health()
        out = []
        for i in range(self.n):
            st = self.state[i]
            if st is Health.OK and not self.observed[i]:
                hs, conf = HealthState.UNKNOWN, 0.0
            else:
                hs = to_health_state(st)
                conf = 1.0 if st is Health.FAILED else float(
                    np.clip(self.g[i] / self.g_max if st is Health.DEGRADED
                            else 1.0 - self.g[i] / max(self.h_degraded, 1e-9) * 0.5, 0.0, 1.0))
            out.append(ComponentHealth(ids[i], hs, float(h[i]), conf, self.reason[i], timestamp))
        return out


@dataclass
class SurfaceMonitor:
    """Komutlanan (nominal model) ve ölçülen yüzey konumu artığı.

    Kalıcı artık -> FAILED (takılı ya da devre dışı). Yüzey verim kaybı
    yalnızca konumdan gözlenemez; bu sınırlama bilinçli olarak belgelenir.
    """
    n: int = 4
    tol: float = 0.15            # normalize konum (|u| <= 1)
    persistence: int = 25        # 50 Hz'de 0,5 s

    def __post_init__(self):
        self._count = np.zeros(self.n, dtype=int)
        self.failed = np.zeros(self.n, dtype=bool)

    def update(self, pos_expected: np.ndarray, pos_meas: np.ndarray) -> np.ndarray:
        r = np.abs(np.asarray(pos_meas, float) - np.asarray(pos_expected, float))
        self._count = np.where(r > self.tol, self._count + 1, 0)
        self.failed |= self._count >= self.persistence
        return self.health()

    def health(self) -> np.ndarray:
        return np.where(self.failed, 0.0, 1.0)

    def reports(self, timestamp: float, ids: list[str] | None = None) -> list[ComponentHealth]:
        ids = ids or [f"surface{i}" for i in range(self.n)]
        return [ComponentHealth(ids[i], HealthState.FAILED if self.failed[i] else HealthState.NOMINAL,
                                0.0 if self.failed[i] else 1.0, 1.0,
                                "konum_artigi" if self.failed[i] else "", timestamp)
                for i in range(self.n)]


@dataclass
class TripleLaneVoter:
    tol: float
    persistence: int = 5                  # ardışık uyuşmazlık sayısı
    isolated: list[bool] = field(default_factory=lambda: [False, False, False])

    def __post_init__(self):
        self._miss = [0, 0, 0]

    def vote(self, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
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

    def disagree(self, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> bool:
        """İki şerit kaldığında aralarındaki fark tolerans dışı mı?"""
        lanes = [np.atleast_1d(np.asarray(x, float)) for x in (a, b, c)]
        active = [lanes[i] for i in range(3) if not self.isolated[i]]
        if len(active) != 2:
            return False
        return bool(np.max(np.abs(active[0] - active[1])) > self.tol)
