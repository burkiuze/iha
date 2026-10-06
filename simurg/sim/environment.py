"""Ortam modelleri: rüzgâr, hava yoğunluğu, sıcaklık, görüş meta verisi.

Rastgelelik kullanan modeller (türbülans) dışarıdan verilen açık bir
`numpy.random.Generator` ile çalışır; küresel rastgele durum kullanılmaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from ..core.config import EnvironmentConfig
from ..core.errors import InvalidScenarioError


@dataclass(frozen=True)
class EnvironmentState:
    wind_ned: np.ndarray
    density: float
    temperature_c: float
    visibility_m: float = 10_000.0

    def to_dict(self) -> dict:
        return {"wind_ned": [round(float(w), 4) for w in self.wind_ned],
                "density": round(self.density, 5), "temperature_c": self.temperature_c,
                "visibility_m": self.visibility_m}


class EnvironmentModel(Protocol):
    def bind_rng(self, rng: np.random.Generator) -> None: ...

    def update(self, t: float, dt: float, position_ned: np.ndarray) -> EnvironmentState: ...


class _Turbulence:
    """Birinci derece Gauss-Markov rüzgâr bozucu (basit, Dryden değil)."""

    def __init__(self, std: float, tau_s: float = 2.0) -> None:
        self.std, self.tau = std, tau_s
        self.state = np.zeros(3)
        self.rng: np.random.Generator | None = None

    def step(self, dt: float) -> np.ndarray:
        if self.std <= 0 or self.rng is None:
            return np.zeros(3)
        a = np.exp(-dt / self.tau)
        self.state = a * self.state + self.std * np.sqrt(1 - a * a) * self.rng.standard_normal(3)
        return self.state


@dataclass
class ConstantEnvironment:
    cfg: EnvironmentConfig = field(default_factory=EnvironmentConfig)

    def __post_init__(self) -> None:
        self._turb = _Turbulence(self.cfg.turbulence_std_mps)

    def bind_rng(self, rng: np.random.Generator) -> None:
        self._turb.rng = rng

    def update(self, t: float, dt: float, position_ned: np.ndarray) -> EnvironmentState:
        wind = np.array(self.cfg.wind_ned_mps, float) + self._turb.step(dt)
        return EnvironmentState(wind, self.cfg.air_density_kgm3, self.cfg.temperature_c)


@dataclass
class ScriptedEnvironment:
    """Zaman anahtar karelerinden doğrusal ara değerlenen rüzgâr profili.

    keyframes: [(t_s, (wN, wE, wD)), ...] artan zamanla.
    """
    keyframes: list[tuple[float, tuple[float, float, float]]]
    cfg: EnvironmentConfig = field(default_factory=EnvironmentConfig)

    def __post_init__(self) -> None:
        if not self.keyframes:
            raise InvalidScenarioError("ScriptedEnvironment: en az bir anahtar kare gerekli")
        ts = [k[0] for k in self.keyframes]
        if any(b <= a for a, b in zip(ts, ts[1:])):
            raise InvalidScenarioError("ScriptedEnvironment: zamanlar kesin artan olmalı")
        self._t = np.array(ts)
        self._w = np.array([k[1] for k in self.keyframes], float)
        self._turb = _Turbulence(self.cfg.turbulence_std_mps)

    def bind_rng(self, rng: np.random.Generator) -> None:
        self._turb.rng = rng

    def update(self, t: float, dt: float, position_ned: np.ndarray) -> EnvironmentState:
        wind = np.array([np.interp(t, self._t, self._w[:, i]) for i in range(3)])
        return EnvironmentState(wind + self._turb.step(dt), self.cfg.air_density_kgm3,
                                self.cfg.temperature_c)
