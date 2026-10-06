"""Navigasyon kaynak sağlayıcıları ve `NavigationSolution` üreten sistem.

Her konum kaynağı (GNSS, VIO, arazi referanslı nav, manyetik harita nav, ...)
bağımsız bir `NavigationProvider`'dır. `NavigationSystem`:

  1. Tüm sağlayıcılardan geçerli ölçümleri toplar (kullanılamayanları not eder).
  2. >= 2 kaynak varsa `IntegrityMonitor` ile füzyon + tutarlılık + hata
     dışlama yapar.
  3. 1 kaynak varsa çözüm üretir ama bütünlük DOĞRULANAMAZ (integrity_ok=False).
  4. Hiç kaynak yoksa son güvenilir çözümü hız ile ilerletir (ataletsel
     ilerletme); koruma seviyesi zamanla büyür, integrity_ok=False.

Fail-safe: "geçerli" işaretli ama sonlu olmayan (NaN/Inf) ölçüm kullanılmaz,
kullanılamayan kaynak sayılır. Hiç çözüm yokken bütünlük asla varsayılmaz.

Kapsam: bozulmuş ya da kullanılamayan kaynağın tespiti, güvenli geri dönüş
ve bütünlük izleme. Sinyal üretimi/aldatma teknikleri kapsam dışıdır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from ..core.types import NavigationSolution, SensorMeasurement
from .integrity import IntegrityMonitor, IntegrityResult, PositionFix


class NavigationProvider(Protocol):
    source_id: str

    def provide(self, t: float) -> SensorMeasurement | None: ...


@dataclass
class NavigationSystem:
    providers: list[NavigationProvider]
    monitor: IntegrityMonitor = field(default_factory=IntegrityMonitor)
    min_sources_for_integrity: int = 2
    inertial_drift_mps: float = 2.0      # ataletsel ilerletmede PL büyüme hızı

    def __post_init__(self) -> None:
        self.last: NavigationSolution | None = None
        self.last_integrity: IntegrityResult | None = None   # açıklanabilirlik için
        self._last_fix_t: float | None = None
        self._last_fix_pl = 0.0

    def update(self, t: float, altitude_m: float, velocity_ned: np.ndarray) -> NavigationSolution:
        fixes, unavailable = [], []
        for p in self.providers:
            m = p.provide(t)
            if m is None or not m.valid or not (np.all(np.isfinite(m.value))
                                                 and np.all(np.isfinite(m.covariance))):
                unavailable.append(p.source_id)
            else:
                fixes.append(PositionFix(p.source_id, np.asarray(m.value, float),
                                         np.asarray(m.covariance, float)))
        al = self.monitor.alert_limit_m
        vel = np.asarray(velocity_ned, float)
        if len(fixes) >= self.min_sources_for_integrity:
            r = self.monitor.evaluate(fixes)
            self.last_integrity = r
            ne, pl, ok = r.position, r.protection_level_m, r.integrity_ok
            used, rejected = tuple(r.used), tuple(r.excluded)
            self._last_fix_t, self._last_fix_pl = t, pl
        elif len(fixes) == 1:
            self.last_integrity = None
            f = fixes[0]
            ne = f.pos
            pl = float(5.45 * np.sqrt(np.max(np.linalg.eigvalsh(f.cov))))
            ok, used, rejected = False, (f.source,), ()
            self._last_fix_t, self._last_fix_pl = t, pl
        else:
            self.last_integrity = None
            if self.last is None:
                ne, pl = np.zeros(2), float("inf")
            else:
                dt = t - self.last.timestamp
                ne = self.last.position_ned[:2] + vel[:2] * dt
                age = t - (self._last_fix_t if self._last_fix_t is not None else t)
                pl = self._last_fix_pl + self.inertial_drift_mps * age
            ok, used, rejected = False, (), ()
        conf = float(np.clip(1.0 - pl / al, 0.0, 1.0)) * (1.0 if ok else 0.5) if np.isfinite(pl) else 0.0
        sol = NavigationSolution(np.array([ne[0], ne[1], -altitude_m]), vel.copy(), conf,
                                 float(pl), used, rejected, tuple(unavailable), bool(ok), t)
        self.last = sol
        return sol
