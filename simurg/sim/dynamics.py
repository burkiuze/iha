"""6-DOF rijit cisim dinamiği ve değiştirilebilir integratörler.

    durum + kuvvetler + momentler -> durum türevi

`RigidBodyDynamics.derivative` saf bir fonksiyondur; kuvvetleri üreten model
(`ForceModel`) dışarıdan verilir. Böylece aerodinamik, itki ve paraşüt
modelleri dinamikten bağımsız olarak değiştirilebilir.

Model belirsizliği: Düz, dönmeyen Dünya; sabit kütle ve atalet; esnek
yapı, yakıt hareketi, jiroskopik pervane etkileri yok.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

import numpy as np

from ..core.config import VehicleConfig
from ..core.errors import ConfigurationError, SimulationError
from ..core.frames import cross3, quat_derivative, quat_normalize, quat_to_dcm

G_NED = np.array([0.0, 0.0, 9.80665])


@dataclass(frozen=True)
class MassProperties:
    mass_kg: float
    inertia: np.ndarray

    @classmethod
    def from_vehicle(cls, v: VehicleConfig) -> "MassProperties":
        return cls(v.mass_kg, v.inertia)

    @property
    def inertia_inv(self) -> np.ndarray:
        return np.linalg.inv(self.inertia)


@dataclass(frozen=True)
class Wrench:
    force_body: np.ndarray
    moment_body: np.ndarray
    force_world: np.ndarray       # gövdeye bağlı olmayan kuvvetler (ör. paraşüt)


ForceModel = Callable[[np.ndarray], Wrench]


class DynamicsModel(Protocol):
    def derivative(self, x: np.ndarray, w: Wrench) -> np.ndarray: ...


class RigidBodyDynamics:
    def __init__(self, mass: MassProperties) -> None:
        self.m = mass.mass_kg
        self.J = mass.inertia
        self.Jinv = mass.inertia_inv

    def derivative(self, x: np.ndarray, w: Wrench) -> np.ndarray:
        q = x[6:10]
        omega = x[10:13]
        R = quat_to_dcm(q)
        acc = (R @ w.force_body + w.force_world) / self.m + G_NED
        qdot = quat_derivative(q, omega)
        wdot = self.Jinv @ (w.moment_body - cross3(omega, self.J @ omega))
        return np.concatenate([x[3:6], acc, qdot, wdot])


class Integrator(Protocol):
    name: str

    def step(self, f: Callable[[np.ndarray], np.ndarray], x: np.ndarray, dt: float) -> np.ndarray: ...


class EulerIntegrator:
    name = "euler"

    def step(self, f, x, dt):
        return x + dt * f(x)


class RK4Integrator:
    name = "rk4"

    def step(self, f, x, dt):
        k1 = f(x)
        k2 = f(x + 0.5 * dt * k1)
        k3 = f(x + 0.5 * dt * k2)
        k4 = f(x + dt * k3)
        return x + dt / 6.0 * (k1 + 2 * k2 + 2 * k3 + k4)


INTEGRATORS: dict[str, type] = {"euler": EulerIntegrator, "rk4": RK4Integrator}


def make_integrator(name: str) -> Integrator:
    try:
        return INTEGRATORS[name]()
    except KeyError:
        raise ConfigurationError(f"bilinmeyen integratör: {name}") from None


def integrate(dyn: DynamicsModel, forces: ForceModel, integ: Integrator,
              x: np.ndarray, dt: float) -> np.ndarray:
    """Tek adım; kuaterniyon normalize edilir, sayısal bozulma yakalanır."""
    xn = integ.step(lambda s: dyn.derivative(s, forces(s)), x, dt)
    if not np.all(np.isfinite(xn)):
        raise SimulationError("durum vektöründe NaN/Inf")
    xn[6:10] = quat_normalize(xn[6:10])
    return xn
