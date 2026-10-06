"""Aerodinamik model arayüzü ve iki uygulama.

    AerodynamicModel (Protocol)
      ├─ AnalyticAeroModel : kapalı form, ±180° hücum açısı (düz levha harmanı)
      └─ TableAeroModel    : CL/CD/Cm(α) tabloları + analitik yanal türevler

Girdi: gövde çerçevesinde hava-göreli hız, açısal hızlar, elevon sapmaları,
hava yoğunluğu. Çıktı: gövde çerçevesinde kuvvet ve moment (AM etrafında).

Sınırlamalar (bilinçli):
  * Pervane akımının kanat üzerindeki etkisi (blown wing) burada YOK;
    elevonlar üzerindeki pervane akımı itki modelinde ayrıca ele alınır.
  * Yer etkisi, kanatlar arası girişim ayrıntısı, kararsız aerodinamik yok.
  * Katsayılar sentetiktir (bkz. coefficients.py).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from .coefficients import AeroCoefficients
from .lookup import Table1D

_MIN_SPEED = 0.5


@dataclass(frozen=True)
class AeroInputs:
    v_air_body: np.ndarray            # (3,) m/s, hava-göreli hız (gövde)
    omega_body: np.ndarray            # (3,) rad/s
    elevon_deflection_rad: np.ndarray  # (4,) pozitif = taşıma artışı
    density: float
    elevon_y_m: np.ndarray            # (4,) açıklık konumları
    elevon_x_m: float                 # burun ekseni boyunca konum
    elevon_area_m2: float
    elevon_cl_delta: float


@dataclass(frozen=True)
class AeroOutput:
    force_body: np.ndarray
    moment_body: np.ndarray
    airspeed: float
    alpha_rad: float
    beta_rad: float
    cl: float = 0.0
    cd: float = 0.0


class AerodynamicModel(Protocol):
    coefficients: AeroCoefficients

    def evaluate(self, inp: AeroInputs) -> AeroOutput: ...


def air_angles(v_b: np.ndarray) -> tuple[float, float, float]:
    V = float(np.linalg.norm(v_b))
    if V < _MIN_SPEED:
        return V, 0.0, 0.0
    alpha = math.atan2(v_b[2], v_b[0])
    beta = math.asin(max(min(float(v_b[1]) / V, 1.0), -1.0))
    return V, alpha, beta


def stall_blend(alpha: float, c: AeroCoefficients) -> float:
    """0: bağlı akım, 1: tam ayrılmış akım (sigmoid)."""
    x = (abs(alpha) - c.alpha_stall_rad) / c.stall_blend_width_rad
    return 1.0 / (1.0 + math.exp(-max(min(x, 50.0), -50.0)))


def analytic_longitudinal(alpha: float, c: AeroCoefficients) -> tuple[float, float, float]:
    """(CL, CD, Cm) — bağlı akım ve düz levha modellerinin harmanı."""
    s = stall_blend(alpha, c)
    a_lin = max(min(alpha, c.alpha_stall_rad * 1.3), -c.alpha_stall_rad * 1.3)
    cl_att = c.cl0 + c.cl_alpha_per_rad * a_lin
    cd_att = c.cd0 + c.induced_k * cl_att ** 2
    cl_fp = c.flat_plate_cn * math.sin(alpha) * math.cos(alpha)
    cd_fp = c.cd0 + c.flat_plate_cn * math.sin(alpha) ** 2
    cm_att = c.cm0 + c.cm_alpha_per_rad * a_lin
    cm_fp = c.cm0 + c.cm_alpha_per_rad * 0.5 * math.sin(alpha)
    return ((1 - s) * cl_att + s * cl_fp, (1 - s) * cd_att + s * cd_fp,
            (1 - s) * cm_att + s * cm_fp)


@dataclass
class AnalyticAeroModel:
    coefficients: AeroCoefficients = field(default_factory=AeroCoefficients)

    def coefficients_at(self, alpha: float) -> tuple[float, float, float]:
        return analytic_longitudinal(alpha, self.coefficients)

    def evaluate(self, inp: AeroInputs) -> AeroOutput:
        return _assemble(inp, self.coefficients, self.coefficients_at)


@dataclass
class TableAeroModel:
    """CL, CD, Cm hücum açısı tablolarından (radyan) çalışır.

    Yanal türevler ve sönüm terimleri `coefficients` içinden alınır. Tablo
    kapsamı dışında değer kırpılır.
    """
    cl: Table1D
    cd: Table1D
    cm: Table1D
    coefficients: AeroCoefficients = field(default_factory=AeroCoefficients)

    @classmethod
    def from_model(cls, model: AnalyticAeroModel, alphas_rad: np.ndarray) -> "TableAeroModel":
        vals = np.array([model.coefficients_at(float(a)) for a in alphas_rad])
        return cls(Table1D(alphas_rad, vals[:, 0]), Table1D(alphas_rad, vals[:, 1]),
                   Table1D(alphas_rad, vals[:, 2]), model.coefficients)

    def coefficients_at(self, alpha: float) -> tuple[float, float, float]:
        return self.cl(alpha), self.cd(alpha), self.cm(alpha)

    def evaluate(self, inp: AeroInputs) -> AeroOutput:
        return _assemble(inp, self.coefficients, self.coefficients_at)


def _assemble(inp: AeroInputs, c: AeroCoefficients, longitudinal) -> AeroOutput:
    v_b = np.asarray(inp.v_air_body, float)
    V, alpha, beta = air_angles(v_b)
    zero = np.zeros(3)
    if V < _MIN_SPEED:
        return AeroOutput(zero, zero.copy(), V, 0.0, 0.0)
    qbar = 0.5 * inp.density * V * V
    S, b, cbar = c.wing_area_m2, c.span_m, c.chord_m
    cl, cd, cm = longitudinal(alpha)
    k = qbar * S
    u, v, w = float(v_b[0]) / V, float(v_b[1]) / V, float(v_b[2]) / V
    sa, ca = math.sin(alpha), math.cos(alpha)
    fx = k * (-cd * u + cl * sa)
    fy = k * (-cd * v + c.cy_beta_per_rad * beta)
    fz = k * (-cd * w - cl * ca)

    p, q, r = (float(x) for x in inp.omega_body)
    Veff = max(V, 1.0)
    roll = c.cl_beta_per_rad * beta + c.cl_p * p * b / (2 * Veff)
    pitch = cm + c.cm_q * q * cbar / (2 * Veff)
    yaw = c.cn_beta_per_rad * beta + c.cn_r * r * b / (2 * Veff)
    mx, my, mz = k * b * roll, k * cbar * pitch, k * b * yaw

    # Elevonların aerodinamik katkısı: kanat normali boyunca (-b_z) kuvvet
    d = inp.elevon_deflection_rad
    if len(d):
        f = qbar * inp.elevon_area_m2 * inp.elevon_cl_delta * np.asarray(d, float)   # (4,)
        fs = float(f.sum())
        fz -= fs
        mx -= float(np.dot(inp.elevon_y_m, f))
        my += inp.elevon_x_m * fs
    return AeroOutput(np.array([fx, fy, fz]), np.array([mx, my, mz]), V, alpha, beta, cl, cd)
