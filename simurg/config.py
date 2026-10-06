"""SİMURG platform sabitleri ve geometri.

Eksen takımı (askı / hover çerçevesi, kuyruk üstü duruşta):
  z : yukarı (itki yönü)
  x : kanat düzlemine dik (seyirde gövdenin "yukarı" ekseni). Üst kanat +x,
      alt kanat -x tarafındadır.
  y : kanat açıklığı yönü (sağ kanat +y)

Moment işaretleri sağ el kuralına göredir: Mx=yuvarlanma (roll),
My=yunuslama (pitch), Mz=sapma (yaw). Bkz. docs/06-ucus-kontrol.md.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

G = 9.80665          # m/s^2
RHO_SL = 1.225       # kg/m^3, deniz seviyesi ISA

MTOW_KG = 24.9
WEIGHT_N = MTOW_KG * G

KQ = 0.016           # m, pervane tork/itki oranı
ELEVON_ARM_Z = 0.35  # m, elevon basınç merkezinin AM altındaki mesafesi (hover)


@dataclass(frozen=True)
class MotorSpec:
    name: str
    x: float           # m
    y: float           # m
    spin: int          # +1 CCW (yukarıdan bakış), -1 CW
    max_thrust: float  # N
    folding: bool      # seyirde katlanan pervane mi


@dataclass(frozen=True)
class SurfaceSpec:
    name: str
    x: float
    y: float
    max_force: float   # N, pervane akımı içinde tam sapmada yanal kuvvet


def default_motors() -> list[MotorSpec]:
    """Kutu kanat üzerindeki 8 motor (her kanatta 4).

    İç motorlar (|y|=0.45) katlanır pervanelidir; seyirde durdurulur.
    Dönüş yönleri, hem hover'da hem seyirde (yalnız dış motorlar) tork
    dengesini koruyacak şekilde çapraz dağıtılmıştır.
    """
    t = 49.0  # N; 8 x 49 N = 392 N -> T/W ~ 1.6
    ys = (-1.20, -0.45, 0.45, 1.20)
    upper_spin = (+1, -1, +1, -1)
    lower_spin = (-1, +1, -1, +1)
    motors = []
    for i, y in enumerate(ys):
        motors.append(MotorSpec(f"M{i + 1}U", +0.30, y, upper_spin[i], t, abs(y) < 1.0))
    for i, y in enumerate(ys):
        motors.append(MotorSpec(f"M{i + 1}L", -0.30, y, lower_spin[i], t, abs(y) < 1.0))
    return motors


def default_surfaces() -> list[SurfaceSpec]:
    """Her kanatta iki elevon; hover'da pervane akımı içinde çalışırlar."""
    return [
        SurfaceSpec("E1U", +0.30, -0.80, 6.0),
        SurfaceSpec("E2U", +0.30, +0.80, 6.0),
        SurfaceSpec("E1L", -0.30, -0.80, 6.0),
        SurfaceSpec("E2L", -0.30, +0.80, 6.0),
    ]


def hover_effectiveness(motors: list[MotorSpec] | None = None,
                        surfaces: list[SurfaceSpec] | None = None
                        ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Hover etkinlik matrisi B (4 x n), alt ve üst sınırlar.

    Satırlar: [Fz, Mx, My, Mz]. Motor girdileri [0, 1] (normalize itki),
    yüzey girdileri [-1, 1] (normalize sapma).
    """
    motors = default_motors() if motors is None else motors
    surfaces = default_surfaces() if surfaces is None else surfaces
    cols, lo, hi = [], [], []
    for m in motors:
        t = m.max_thrust
        cols.append([t, m.y * t, -m.x * t, KQ * m.spin * t])
        lo.append(0.0)
        hi.append(1.0)
    for s in surfaces:
        f = s.max_force
        # Kuvvet +x yönünde, uygulama noktası (x, y, -h):
        # r x F = (0, -h F, -y F)
        cols.append([0.0, 0.0, -ELEVON_ARM_Z * f, -s.y * f])
        lo.append(-1.0)
        hi.append(1.0)
    return np.array(cols).T, np.array(lo), np.array(hi)
