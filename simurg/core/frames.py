"""Eksen takımları ve kuaterniyon yardımcıları.

Dünya çerçevesi: NED (x kuzey, y doğu, z aşağı). İrtifa = -z.

Gövde çerçevesi (FRD benzeri, tail-sitter için tanım):
  b_x : burun = itki ekseni (seyirde ileri, askıda yukarı)
  b_y : sağ kanat açıklığı
  b_z : b_x x b_y (seyirde aşağı; askıda gövdenin "karın" yönü)

Askı (hover) tahsis çerçevesi h ile ilişki (bkz. simurg/config.py):
  h_z = b_x,  h_y = b_y,  h_x = -b_z
Dolayısıyla gövde moment vektörü M_b = (Mz_h, My_h, -Mx_h).

Kuaterniyon: q = [w, x, y, z], gövde -> dünya dönüşümü (Hamilton).
"""

from __future__ import annotations

import math

import numpy as np


def quat_mul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return np.array([aw * bw - ax * bx - ay * by - az * bz,
                     aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw])


def quat_conj(q: np.ndarray) -> np.ndarray:
    return np.array([q[0], -q[1], -q[2], -q[3]])


def quat_normalize(q: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(q))
    if n < 1e-12:
        return np.array([1.0, 0.0, 0.0, 0.0])
    return q / n


def quat_to_dcm(q: np.ndarray) -> np.ndarray:
    """Gövde -> dünya dönüşüm matrisi R (v_dünya = R @ v_gövde)."""
    w, x, y, z = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])


def quat_from_euler(yaw: float, pitch: float, roll: float) -> np.ndarray:
    """ZYX (yaw-pitch-roll) Euler açılarından kuaterniyon [rad]."""
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cr, sr = math.cos(roll / 2), math.sin(roll / 2)
    return np.array([cr * cp * cy + sr * sp * sy,
                     sr * cp * cy - cr * sp * sy,
                     cr * sp * cy + sr * cp * sy,
                     cr * cp * sy - sr * sp * cy])


def quat_derivative(q: np.ndarray, omega_b: np.ndarray) -> np.ndarray:
    return 0.5 * quat_mul(q, np.array([0.0, *omega_b]))


def attitude_angles(R: np.ndarray) -> tuple[float, float, float]:
    """Tail-sitter için tekilliksiz (yönsel) açılar [rad]: (heading, pitch, bank).

    pitch : burnun ufuk üzerindeki açısı (askıda +90°)
    bank  : kanat açıklığı ekseninin ufka göre eğimi (sağ kanat aşağı +)
    heading: burun ve karın eksenlerinin ağırlıklı yatay izdüşümü;
             hem seyirde hem askıda sürekli tanımlıdır.
    """
    sp = max(min(-float(R[2, 0]), 1.0), -1.0)
    pitch = math.asin(sp)
    bank = math.asin(max(min(float(R[2, 1]), 1.0), -1.0))
    cp = math.sqrt(max(1.0 - sp * sp, 0.0))
    v = R[:, 0] * cp + R[:, 2] * sp
    heading = math.atan2(v[1], v[0])
    return heading, pitch, bank


def cross3(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """3-B vektörel çarpım (np.cross'tan küçük diziler için çok daha hızlı)."""
    a0, a1, a2 = float(a[0]), float(a[1]), float(a[2])
    b0, b1, b2 = float(b[0]), float(b[1]), float(b[2])
    return np.array([a1 * b2 - a2 * b1, a2 * b0 - a0 * b2, a0 * b1 - a1 * b0])


def wrap_pi(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi
