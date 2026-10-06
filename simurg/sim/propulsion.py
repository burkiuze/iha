"""Dağıtık elektrik itki modeli (simülasyon).

* Motor itkisi: T_i = u_i * T_max * s(V),  s(V) = max(1 - V_ax/V0, 0.15)
* Elevonlar üzerindeki pervane akımı kuvveti: F_wash = F0 * min(T_top/W, 1.5)
* Elektrik gücü (momentum teorisi): P_i = T_i (V_ax + v_i) / η,
  v_i = -V_ax/2 + sqrt((V_ax/2)^2 + T_i / (2 ρ A))

Değerler sentetiktir; motor/ESC/pervane karakterizasyonu yerine geçmez.
"""

from __future__ import annotations

import math

import numpy as np

from ..core.config import VehicleConfig


class PropulsionModel:
    def __init__(self, vehicle: VehicleConfig) -> None:
        v = vehicle
        self.v = v
        self.tmax = np.array([m.max_thrust for m in v.motors])
        self.mx = np.array([m.x for m in v.motors])     # h-çerçevesi x (kanat normali)
        self.my = np.array([m.y for m in v.motors])
        self.spin = np.array([m.spin for m in v.motors], dtype=float)
        self.sy = np.array([s.y for s in v.surfaces])
        self.disk_area = math.pi * (v.prop_diameter_m / 2) ** 2

    def thrust_scale(self, v_axial: float) -> float:
        return max(1.0 - max(v_axial, 0.0) / self.v.prop_zero_thrust_speed_mps, 0.15)

    def thrusts(self, u_motor: np.ndarray, v_axial: float) -> np.ndarray:
        return np.minimum(np.maximum(u_motor, 0.0), 1.0) * (self.tmax * self.thrust_scale(v_axial))

    def wash_force(self, thrusts: np.ndarray) -> float:
        return self.v.prop_wash_force_n * min(float(np.sum(thrusts)) / self.v.weight_n, 1.5)

    def wrench_body(self, thrusts: np.ndarray, u_surface: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """İtki + motor torku + pervane akımı elevon etkisi (gövde)."""
        v = self.v
        fz_h = float(np.sum(thrusts))
        mx_h = float(np.dot(self.my, thrusts))
        my_h = float(np.dot(-self.mx, thrusts))
        mz_h = float(np.dot(v.torque_coeff_m * self.spin, thrusts))
        f_wash = self.wash_force(thrusts) * np.asarray(u_surface, float)
        force = np.array([fz_h, 0.0, -float(np.sum(f_wash))])
        moment = np.array([mz_h - float(np.dot(self.sy, f_wash)),
                           my_h + v.elevon_x_m * float(np.sum(f_wash)),
                           -mx_h])
        return force, moment

    def electrical_power(self, thrusts: np.ndarray, v_axial: float, density: float) -> float:
        va = max(v_axial, 0.0)
        t = np.maximum(thrusts, 0.0)
        vi = -va / 2 + np.sqrt((va / 2) ** 2 + t / (2 * density * self.disk_area))
        return float(np.sum(t * (va + vi)) / self.v.propulsive_efficiency)
