"""Simülasyon iç döngü kontrolcüsü (araştırma amaçlı, ayarlanmamış).

Bu modül 6-DOF dijital ikizi kapalı döngüde uçurabilmek için yazılmış
basit bir kademeli kontrolcüdür; gerçek araca uygulanacak kontrol yasası
ya da kazanç seti DEĞİLDİR. Kazançlar yalnızca sentetik modelde kararlı
davranış için seçilmiştir.

  istenen tutum (heading, pitch, bank, yanal eğim)
        │ kuaterniyon hatası (tekilliksiz, askıda da geçerli)
        ▼
  açısal hız komutu ─► açısal ivme komutu ─► M = J α + ω × Jω
        +
  itki: askı/geçişte dikey ivme yasası, seyirde hava hızı PI
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..core.config import VehicleConfig
from ..core.frames import cross3, quat_conj, quat_from_euler, quat_mul

G = 9.80665


@dataclass(frozen=True)
class AttitudeSetpoint:
    heading_rad: float
    pitch_rad: float
    bank_rad: float = 0.0
    lateral_tilt_rad: float = 0.0      # askıda burnun yana eğimi (b_z etrafında)

    def quaternion(self) -> np.ndarray:
        q = quat_from_euler(self.heading_rad, self.pitch_rad, self.bank_rad)
        if self.lateral_tilt_rad:
            h = 0.5 * self.lateral_tilt_rad
            q = quat_mul(q, np.array([math.cos(h), 0.0, 0.0, math.sin(h)]))
        return q


@dataclass(frozen=True)
class ControllerGains:
    att_kp: tuple[float, float, float] = (2.5, 4.0, 3.0)      # 1/s
    rate_kp: tuple[float, float, float] = (6.0, 12.0, 8.0)    # 1/s
    max_rate_rad_s: tuple[float, float, float] = (1.5, 1.5, 1.2)
    alt_kp: float = 1.0          # (m/s^2)/m
    climb_kp: float = 1.8        # (m/s^2)/(m/s)
    max_vertical_acc: float = 4.0
    pos_kp: float = 0.25         # askıda yatay konum (m/s^2)/m
    pos_kd: float = 0.9
    max_horizontal_acc: float = 3.0
    speed_kp: float = 6.0        # N/(m/s) per kg
    speed_ki: float = 0.6


@dataclass(frozen=True)
class FlightDemand:
    thrust_n: float
    moment_body: np.ndarray
    attitude_error_deg: float


class FlightController:
    def __init__(self, vehicle: VehicleConfig | None = None,
                 gains: ControllerGains | None = None) -> None:
        self.v = vehicle or VehicleConfig()
        self.g = gains or ControllerGains()
        self.J = self.v.inertia
        self._speed_int = 0.0

    # ---- tutum ------------------------------------------------------------
    def attitude_moment(self, q: np.ndarray, omega: np.ndarray,
                        sp: AttitudeSetpoint) -> tuple[np.ndarray, float]:
        qd = sp.quaternion()
        qe = quat_mul(quat_conj(qd), q)
        if qe[0] < 0:
            qe = -qe
        err = 2.0 * qe[1:]
        ang = math.degrees(2.0 * math.acos(min(abs(qe[0]), 1.0)))
        w_cmd = np.clip(-np.array(self.g.att_kp) * err,
                        -np.array(self.g.max_rate_rad_s), np.array(self.g.max_rate_rad_s))
        alpha = np.array(self.g.rate_kp) * (w_cmd - omega)
        M = self.J @ alpha + cross3(omega, self.J @ omega)
        return M, ang

    # ---- itki yasaları ------------------------------------------------------
    def vertical_thrust(self, altitude: float, climb: float, alt_cmd: float,
                        climb_limit: tuple[float, float], pitch_rad: float,
                        aero_up_n: float, max_thrust_n: float) -> float:
        """Askı/geçiş: dikey ivme isteği -> itki (burun ekseni boyunca)."""
        g = self.g
        climb_cmd = float(np.clip(g.alt_kp * (alt_cmd - altitude), *climb_limit))
        a = float(np.clip(g.climb_kp * (climb_cmd - climb), -g.max_vertical_acc,
                          g.max_vertical_acc))
        need = self.v.mass_kg * (G + a) - aero_up_n
        return float(np.clip(need / max(math.sin(pitch_rad), 0.25), 0.0, max_thrust_n))

    def speed_thrust(self, airspeed: float, airspeed_cmd: float, pitch_rad: float,
                     drag_n: float, dt: float, max_thrust_n: float) -> float:
        """Seyir: hava hızı PI + sürükleme ve ağırlık bileşeni ileri beslemesi."""
        m = self.v.mass_kg
        e = airspeed_cmd - airspeed
        self._speed_int = float(np.clip(self._speed_int + e * dt, -20.0, 20.0))
        T = drag_n + m * G * math.sin(pitch_rad) + m * (self.g.speed_kp * 0.1 * e
                                                         + self.g.speed_ki * 0.1 * self._speed_int)
        return float(np.clip(T, 0.0, max_thrust_n))

    def hover_tilt(self, pos_ne: np.ndarray, vel_ne: np.ndarray, target_ne: np.ndarray,
                   heading_rad: float) -> tuple[float, float]:
        """Askıda yatay konum tutma: (burun ileri eğimi, yanal eğim) [rad]."""
        g = self.g
        a = g.pos_kp * (target_ne - pos_ne) - g.pos_kd * vel_ne
        n = float(np.linalg.norm(a))
        if n > g.max_horizontal_acc:
            a = a * (g.max_horizontal_acc / n)
        ch, sh = math.cos(heading_rad), math.sin(heading_rad)
        a_fwd = a[0] * ch + a[1] * sh
        a_lat = -a[0] * sh + a[1] * ch
        return math.atan2(a_fwd, G), math.atan2(a_lat, G)

    def reset_integrators(self) -> None:
        self._speed_int = 0.0
