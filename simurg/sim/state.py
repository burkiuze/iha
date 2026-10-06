"""Rijit cisim durum vektörü (integratörün gördüğü ham durum).

Merkezi, zengin durum `simurg.core.types.VehicleState`'tir; bu sınıf yalnızca
6-DOF integrasyonu için gereken 13 elemanlı vektörü taşır:
    [p_N, p_E, p_D, v_N, v_E, v_D, q_w, q_x, q_y, q_z, p, q, r]
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..core.frames import quat_normalize, quat_to_dcm

STATE_SIZE = 13


@dataclass
class RigidBodyState:
    position_ned: np.ndarray
    velocity_ned: np.ndarray
    quaternion: np.ndarray
    omega_body: np.ndarray

    def to_vector(self) -> np.ndarray:
        return np.concatenate([self.position_ned, self.velocity_ned,
                               self.quaternion, self.omega_body])

    @classmethod
    def from_vector(cls, x: np.ndarray) -> "RigidBodyState":
        return cls(x[0:3].copy(), x[3:6].copy(), quat_normalize(x[6:10].copy()), x[10:13].copy())

    @property
    def dcm(self) -> np.ndarray:
        return quat_to_dcm(self.quaternion)

    def copy(self) -> "RigidBodyState":
        return RigidBodyState.from_vector(self.to_vector())
