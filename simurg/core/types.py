"""Modüller arası ortak veri sözleşmeleri.

Bu modül yalnızca NumPy ve standart kütüphaneye bağlıdır; paketin başka hiçbir
modülünü içe aktarmaz. Böylece `control`, `power`, `nav`, `fdir`, `safety`
ve `sim` döngüsel bağımlılık oluşturmadan aynı tipleri paylaşır.

Birimler SI'dır (m, s, kg, N, W, J); yalnızca insan okumasına yönelik
`*_deg` ve `*_wh` adlı alanlar istisnadır ve adlarında belirtilir.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

from .frames import attitude_angles, quat_to_dcm


class HealthState(str, Enum):
    NOMINAL = "nominal"
    DEGRADED = "degraded"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ComponentHealth:
    """FDIR'in her bileşen için ürettiği standart sağlık raporu."""
    component_id: str
    state: HealthState
    health_score: float        # 0 (işlevsiz) .. 1 (nominal)
    confidence: float          # 0 .. 1, kestirimin güveni
    reason: str
    timestamp: float

    def to_dict(self) -> dict[str, Any]:
        return {"component_id": self.component_id, "state": self.state.value,
                "health_score": round(self.health_score, 6),
                "confidence": round(self.confidence, 6), "reason": self.reason,
                "timestamp": round(self.timestamp, 6)}


@dataclass(frozen=True)
class EnergyState:
    """Enerji alt sisteminin anlık özeti (SI; enerji J, güç W)."""
    available_energy_j: float      # rezerv hariç kullanılabilir enerji
    reserve_energy_j: float        # batarya rezervi (yalnızca acil durumda)
    battery_soc: float
    fuel_cell_power_w: float
    fuel_cell_available: bool
    hydrogen_energy_j: float       # kalan kimyasal enerji
    supercap_soc: float
    solar_input_w: float
    power_demand_w: float
    unmet_power_w: float
    health: float                  # 0..1, kaynak bozunumunun özeti

    def to_dict(self) -> dict[str, Any]:
        return {k: (round(v, 6) if isinstance(v, float) else v)
                for k, v in self.__dict__.items()}


@dataclass(frozen=True)
class NavigationSolution:
    """Navigasyon sisteminin çıktısı: konum değil, bütünlük bilgili çözüm."""
    position_ned: np.ndarray          # (3,) m
    velocity_ned: np.ndarray          # (3,) m/s
    confidence: float                 # 0..1 (1 - PL/alarm limiti, kırpılmış)
    protection_level_m: float
    sources_used: tuple[str, ...]
    sources_rejected: tuple[str, ...]
    sources_unavailable: tuple[str, ...]
    integrity_ok: bool
    timestamp: float

    def to_dict(self) -> dict[str, Any]:
        return {"position_ned": [round(float(x), 4) for x in self.position_ned],
                "velocity_ned": [round(float(x), 4) for x in self.velocity_ned],
                "confidence": round(self.confidence, 6),
                "protection_level_m": round(self.protection_level_m, 4),
                "sources_used": list(self.sources_used),
                "sources_rejected": list(self.sources_rejected),
                "sources_unavailable": list(self.sources_unavailable),
                "integrity_ok": self.integrity_ok,
                "timestamp": round(self.timestamp, 6)}


@dataclass
class VehicleState:
    """Merkezi araç durumu (tek doğruluk kaynağı).

    Simülasyonda motor her adımda bu nesneyi doldurur; RTA, mod makinesi,
    kayıt ve metrikler bu nesneden türetilen görünümleri kullanır.
    `flight_mode` döngüsel bağımlılığı önlemek için `Mode.name` dizgesidir.
    """
    time_s: float
    position_ned: np.ndarray
    velocity_ned: np.ndarray
    quaternion: np.ndarray
    angular_rate_body: np.ndarray
    airspeed_mps: float = 0.0
    groundspeed_mps: float = 0.0
    energy: EnergyState | None = None
    nav_integrity_ok: bool = True
    link_ok: bool = True
    actuator_health: np.ndarray = field(default_factory=lambda: np.ones(12))
    flight_mode: str = "PREFLIGHT"
    landed: bool = True

    # ---- türetilmiş görünümler ------------------------------------------
    @property
    def altitude_m(self) -> float:
        return float(-self.position_ned[2])

    @property
    def climb_mps(self) -> float:
        return float(-self.velocity_ned[2])

    @property
    def attitude_deg(self) -> tuple[float, float, float]:
        """(heading, pitch, bank) derece."""
        h, p, b = attitude_angles(quat_to_dcm(self.quaternion))
        return math.degrees(h), math.degrees(p), math.degrees(b)

    def snapshot(self) -> dict[str, Any]:
        """Kayıt için kararlı, JSON-uyumlu özet."""
        hdg, pitch, bank = self.attitude_deg
        return {
            "t": round(self.time_s, 6),
            "pos": [round(float(x), 3) for x in self.position_ned],
            "vel": [round(float(x), 3) for x in self.velocity_ned],
            "att_deg": [round(hdg, 3), round(pitch, 3), round(bank, 3)],
            "rates": [round(float(x), 4) for x in self.angular_rate_body],
            "airspeed": round(self.airspeed_mps, 3),
            "groundspeed": round(self.groundspeed_mps, 3),
            "alt": round(self.altitude_m, 3),
            "mode": self.flight_mode,
            "nav_ok": self.nav_integrity_ok,
            "link_ok": self.link_ok,
            "health": [round(float(x), 4) for x in self.actuator_health],
            "soc": None if self.energy is None else round(self.energy.battery_soc, 5),
            "landed": self.landed,
        }


@dataclass(frozen=True)
class SensorMeasurement:
    """Simüle edilmiş sensör ölçümü (marka/model bağımsız)."""
    sensor_id: str
    timestamp: float
    value: np.ndarray
    covariance: np.ndarray
    valid: bool = True
    quality: float = 1.0       # 0..1, sensörün kendi beyan ettiği kalite
    health: float = 1.0        # 0..1, sensör sağlığı (arıza enjeksiyonu)
