"""Eyleyici (motor + kontrol yüzeyi) modeli.

Her eyleyici için:
  * komut gecikmesi (latency, tam adım sayısı)
  * birinci derece tepki (zaman sabiti tau)
  * doyma (alt/üst sınır)
  * arıza modları: DEGRADED (verim kaybı), STUCK (takılı), OFFLINE (devre dışı)

Model paralel olarak arızasız bir "beklenen" (nominal) tepki de hesaplar;
FDIR artığı bu beklenen tepkiye göre oluşturulur (model tabanlı tespit).

Çıkış anlamı: motorlar için normalize itki oranı, yüzeyler için normalize
sapma (etkin kuvvet ölçeği sağlıkla çarpılmış).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum

import numpy as np

from ..core.errors import InvalidScenarioError
from .faults import Fault, FaultKind


class ActuatorMode(str, Enum):
    NOMINAL = "nominal"
    DEGRADED = "degraded"
    STUCK = "stuck"
    OFFLINE = "offline"


@dataclass(frozen=True)
class ActuatorCommand:
    u: np.ndarray
    timestamp: float


@dataclass(frozen=True)
class ActuatorState:
    position: np.ndarray     # fiziksel konum (yüzey) / devir oranı^2 karşılığı (motor)
    output: np.ndarray       # kuvvet üreten etkin çıkış
    expected: np.ndarray     # arızasız nominal model çıkışı
    health_true: np.ndarray  # gerçek (simülasyon) sağlık
    modes: tuple[ActuatorMode, ...]
    timestamp: float


class ActuatorModel:
    def __init__(self, ids: tuple[str, ...], lower: np.ndarray, upper: np.ndarray,
                 tau_s: np.ndarray, latency_s: float, dt: float) -> None:
        self.ids = tuple(ids)
        self.index = {name: i for i, name in enumerate(self.ids)}
        n = len(self.ids)
        self.lower, self.upper = np.asarray(lower, float), np.asarray(upper, float)
        self.alpha = 1.0 - np.exp(-dt / np.asarray(tau_s, float))
        steps = max(int(round(latency_s / dt)), 0)
        self._queue: deque[np.ndarray] = deque([np.zeros(n)] * steps)
        self.pos = np.zeros(n)
        self.nominal = np.zeros(n)
        self.health = np.ones(n)
        self.modes = [ActuatorMode.NOMINAL] * n
        self.stuck_value = np.zeros(n)
        self.last: ActuatorState | None = None

    def step(self, cmd: ActuatorCommand) -> ActuatorState:
        u = np.clip(np.asarray(cmd.u, float), self.lower, self.upper)
        self._queue.append(u)
        u_d = self._queue.popleft()
        self.nominal = self.nominal + self.alpha * (u_d - self.nominal)
        self.pos = self.pos + self.alpha * (u_d - self.pos)
        out = self.pos * self.health
        phys = self.pos.copy()
        for i, m in enumerate(self.modes):
            if m is ActuatorMode.STUCK:
                phys[i] = out[i] = self.stuck_value[i]
                self.pos[i] = self.stuck_value[i]
            elif m is ActuatorMode.OFFLINE:
                phys[i] = out[i] = 0.0
                self.pos[i] = 0.0
        self.last = ActuatorState(phys, out, self.nominal.copy(), self.health.copy(),
                                  tuple(self.modes), cmd.timestamp)
        return self.last

    # ---- FaultTarget ----------------------------------------------------
    def _idx(self, fault: Fault) -> int:
        try:
            return self.index[fault.component]
        except KeyError:
            raise InvalidScenarioError(f"bilinmeyen eyleyici: {fault.component}") from None

    def apply_fault(self, fault: Fault) -> None:
        i = self._idx(fault)
        if fault.kind is FaultKind.ACTUATOR_DEGRADED:
            self.modes[i] = ActuatorMode.DEGRADED
            self.health[i] = 1.0 - fault.severity
        elif fault.kind is FaultKind.ACTUATOR_STUCK:
            self.modes[i] = ActuatorMode.STUCK
            self.stuck_value[i] = float(fault.params.get("position", self.pos[i]))
        elif fault.kind is FaultKind.ACTUATOR_OFFLINE:
            self.modes[i] = ActuatorMode.OFFLINE
        else:
            raise InvalidScenarioError(f"eyleyici bu arıza türünü desteklemiyor: {fault.kind}")

    def clear_fault(self, fault: Fault) -> None:
        i = self._idx(fault)
        self.modes[i] = ActuatorMode.NOMINAL
        self.health[i] = 1.0


def rpm_from_output(output: np.ndarray, rpm_max: float) -> np.ndarray:
    """İtki ~ devir^2 varsayımıyla normalize itki oranından devir."""
    return rpm_max * np.sqrt(np.clip(output, 0.0, None))


def motor_tau_vector(n_motors: int, n_surfaces: int, motor_tau: float,
                     surface_tau: float) -> np.ndarray:
    return np.array([motor_tau] * n_motors + [surface_tau] * n_surfaces)


__all__ = ["ActuatorCommand", "ActuatorMode", "ActuatorModel", "ActuatorState",
           "motor_tau_vector", "rpm_from_output"]
