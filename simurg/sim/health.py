"""Sağlık denetçisi: FDIR izleyicilerini simülasyona bağlar.

* Beklenen (nominal model) ve ölçülen devir/yüzey konumu artığı -> izleyiciler
* Durum değişiminde standart `ComponentHealth` raporu üretir
* Askı (hover) marjını hesaplar (önbellekli)

Fail-safe politikası (unknown != healthy): Hiç gözlenmemiş (UNKNOWN) bir
eyleyici, havadayken askı fizibilitesi hesabında ÇALIŞMIYOR kabul edilir.
Yerde (kalkış öncesi) ESC öz-testinin geçtiği varsayılır; bu varsayım
`docs/14` sınırlamalarında belgelidir. Dağıtıcıya giden sağlık vektörü
son bilinen kestirimdir (komut verilmeden gözlenemeyen motorun komutunu
kesmek, onu gözlemenin önünde engel olurdu).
"""

from __future__ import annotations

import numpy as np

from ..control.allocation import ControlAllocator
from ..control.effectiveness import HoverEffectiveness
from ..core.types import ComponentHealth, HealthState
from ..fdir.monitor import MotorHealthMonitor, SurfaceMonitor
from .actuators import ActuatorState, rpm_from_output


class HealthSupervisor:
    def __init__(self, ids: tuple[str, ...], n_motors: int, rpm_max: float,
                 weight_n: float) -> None:
        self.ids = ids
        self.n_m = n_motors
        self.rpm_max = rpm_max
        self.weight_n = weight_n
        self.motors = MotorHealthMonitor(n=n_motors, min_observable_abs=0.25 * rpm_max)
        self.surfaces = SurfaceMonitor(n=len(ids) - n_motors)
        self.health = np.ones(len(ids))
        self._hover = ControlAllocator.from_regime(HoverEffectiveness().regime())
        self._cache: dict[tuple, float] = {}
        self._sig: tuple | None = None
        self._seen: dict[str, HealthState] = {}
        self.hover_margin = self._margin(self.health)

    def _margin(self, h: np.ndarray) -> float:
        key = tuple(np.round(h, 2))
        if key not in self._cache:
            self._cache[key] = self._hover.hover_margin(self.weight_n, h)
        return self._cache[key]

    @property
    def unknown_mask(self) -> np.ndarray:
        m = np.zeros(len(self.ids), dtype=bool)
        m[:self.n_m] = ~self.motors.observed
        return m

    def update(self, st: ActuatorState, rpm_meas: np.ndarray | None, power_factor: float,
               t: float, airborne: bool) -> list[ComponentHealth]:
        """İzleyicileri günceller; DURUMU DEĞİŞEN bileşenlerin raporlarını döndürür."""
        n = self.n_m
        rpm_exp = rpm_from_output(st.expected[:n] * power_factor, self.rpm_max)
        if rpm_meas is not None:
            self.motors.update(rpm_exp, rpm_meas)
        self.surfaces.update(st.expected[n:], st.position[n:])
        self.health = np.concatenate([self.motors.health(), self.surfaces.health()])
        planning = np.where(self.unknown_mask, 0.0, self.health) if airborne else self.health
        self.hover_margin = self._margin(planning)

        sig = (tuple(self.motors.state), tuple(self.surfaces.failed))
        if sig == self._sig:
            return []
        self._sig = sig
        changed = []
        reports = (self.motors.reports(t, list(self.ids[:n]))
                   + self.surfaces.reports(t, list(self.ids[n:])))
        for r in reports:
            if r.state is HealthState.UNKNOWN or r.state is self._seen.get(r.component_id,
                                                                           HealthState.NOMINAL):
                continue
            self._seen[r.component_id] = r.state
            changed.append(r)
        return changed

    def component_states(self, airborne: bool) -> dict[str, HealthState]:
        """Bileşen kimliği -> sağlık durumu. Gözlenmemiş motor: havadaysa UNKNOWN,
        yerdeyse (ESC öz-testi varsayımı) NOMINAL."""
        out: dict[str, HealthState] = {}
        unknown = self.unknown_mask
        for i, cid in enumerate(self.ids):
            if i < self.n_m:
                st = self.motors.state[i]
                if st.value == "ok":
                    out[cid] = HealthState.UNKNOWN if (unknown[i] and airborne) else HealthState.NOMINAL
                else:
                    out[cid] = HealthState(st.value)
            else:
                out[cid] = HealthState.FAILED if self.surfaces.failed[i - self.n_m] else HealthState.NOMINAL
        return out

    def details(self, component_id: str) -> dict[str, float]:
        """Açıklanabilirlik için izleyici iç durumu (CUSUM, verim kestirimi)."""
        i = self.ids.index(component_id)
        if i < self.n_m:
            return {"cusum": round(float(self.motors.g[i]), 6),
                    "efficiency_estimate": round(float(self.motors.eff[i]), 6),
                    "cusum_threshold": self.motors.h_degraded,
                    "efficiency_fail_threshold": self.motors.eff_failed}
        return {"position_residual_persistence": self.surfaces.persistence}
