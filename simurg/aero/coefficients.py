"""Kutu kanat için SENTETİK aerodinamik katsayılar.

Bu değerler el hesabı ve literatürdeki tipik büyüklüklerden türetilmiş
yer tutuculardır; CFD, rüzgâr tüneli veya uçuş testiyle doğrulanmamıştır.
`provenance` alanı bunu her kayıtta görünür kılar. Gerçek veriler geldiğinde
`TableAeroModel` ile değiştirilmeleri hedeflenir.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class AeroCoefficients:
    provenance: str = "synthetic-v1 (doğrulanmamış tasarım tahmini)"
    wing_area_m2: float = 1.15
    span_m: float = 3.20
    chord_m: float = 0.18
    # boylamsal
    cl0: float = 0.25
    cl_alpha_per_rad: float = 4.5
    alpha_stall_rad: float = math.radians(15.0)
    stall_blend_width_rad: float = math.radians(2.0)
    cd0: float = 0.019
    induced_k: float = 0.0274        # 1/(pi e AR) x kutu kanat faktörü (~0,69)
    flat_plate_cn: float = 1.2       # stall sonrası düz levha normal kuvvet katsayısı
    cm0: float = 0.025
    cm_alpha_per_rad: float = -0.6
    cm_q: float = -8.0
    # yanal
    cy_beta_per_rad: float = -0.6
    cl_beta_per_rad: float = -0.05   # yuvarlanma (b_x ekseni)
    cl_p: float = -0.5
    cn_beta_per_rad: float = 0.08    # sapma (b_z ekseni), uç levhaları
    cn_r: float = -0.12
