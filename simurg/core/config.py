"""Yapılandırma dataclass'ları.

`simurg/config.py` içindeki sabitler geriye dönük uyumluluk için korunur;
buradaki dataclass'lar varsayılanlarını oradan alır. Yeni kod sabitleri
doğrudan değil, bu nesneler üzerinden kullanmalıdır (bağımlılık enjeksiyonu,
Monte Carlo'da parametre değiştirme).

UYARI: Kütle/atalet/itki değerleri kavramsal tasarım tahminleridir; ölçülmüş
ya da doğrulanmış araç verisi DEĞİLDİR.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from .. import config as legacy
from .errors import ConfigurationError


@dataclass(frozen=True)
class VehicleConfig:
    mass_kg: float = legacy.MTOW_KG
    # Gövde eksenlerinde (b_x burun, b_y açıklık, b_z) köşegen atalet [kg m^2].
    # Kaba tahmin: kütlenin büyük kısmı 3,2 m açıklık boyunca dağılmış.
    inertia_diag_kgm2: tuple[float, float, float] = (8.5, 1.2, 9.5)
    motors: tuple[legacy.MotorSpec, ...] = field(
        default_factory=lambda: tuple(legacy.default_motors()))
    surfaces: tuple[legacy.SurfaceSpec, ...] = field(
        default_factory=lambda: tuple(legacy.default_surfaces()))
    torque_coeff_m: float = legacy.KQ
    prop_diameter_m: float = 0.406
    prop_zero_thrust_speed_mps: float = 55.0   # itki ~ (1 - V/V0) azalır
    propulsive_efficiency: float = 0.65        # motor+ESC+pervane (momentum teorisine göre)
    rpm_max: float = 7000.0
    motor_tau_s: float = 0.05
    surface_tau_s: float = 0.03
    actuator_latency_s: float = 0.02
    elevon_x_m: float = -legacy.ELEVON_ARM_Z   # AM'nin arkasında (burun ekseni boyunca)
    elevon_area_m2: float = 0.04
    elevon_cl_delta_per_rad: float = 2.0
    elevon_max_deflection_rad: float = 0.35
    prop_wash_force_n: float = 6.0             # askıda, tam sapmada elevon kuvveti
    avionics_power_w: float = 70.0
    parachute_cds_m2: float = 16.0             # ~5 m/s alçalma

    def __post_init__(self) -> None:
        if self.mass_kg <= 0 or min(self.inertia_diag_kgm2) <= 0:
            raise ConfigurationError("kütle ve atalet pozitif olmalı")
        if len(self.motors) != 8 or len(self.surfaces) != 4:
            raise ConfigurationError("referans model 8 motor + 4 elevon varsayar")

    @property
    def weight_n(self) -> float:
        return self.mass_kg * legacy.G

    @property
    def inertia(self) -> np.ndarray:
        return np.diag(self.inertia_diag_kgm2)

    @property
    def n_actuators(self) -> int:
        return len(self.motors) + len(self.surfaces)

    @property
    def actuator_ids(self) -> tuple[str, ...]:
        return tuple(m.name for m in self.motors) + tuple(s.name for s in self.surfaces)

    def with_mass_scale(self, k: float) -> "VehicleConfig":
        return replace(self, mass_kg=self.mass_kg * k,
                       inertia_diag_kgm2=tuple(i * k for i in self.inertia_diag_kgm2))


@dataclass(frozen=True)
class SimulationConfig:
    dt_s: float = 0.02                 # 50 Hz fizik + kontrol
    nav_period_s: float = 0.2          # 5 Hz navigasyon/bütünlük
    snapshot_period_s: float = 0.5     # kayıt örnekleme
    integrator: str = "rk4"            # "rk4" | "euler"
    stop_when_disarmed: bool = True

    def __post_init__(self) -> None:
        if self.dt_s <= 0 or self.nav_period_s < self.dt_s:
            raise ConfigurationError("dt pozitif, nav periyodu >= dt olmalı")


@dataclass(frozen=True)
class SafetyConfig:
    geofence_radius_m: float = 3000.0
    link_loss_rth_s: float = 30.0
    hover_margin_min: float = 1.05
    energy_warning_factor: float = 1.6     # kullanılabilir / gerekli < bu -> uyarı
    cruise_power_estimate_w: float = 590.0
    loss_of_control_att_err_deg: float = 60.0
    loss_of_control_time_s: float = 2.0
    loiter_timeout_s: float = 300.0
    rta_horizon_s: float = 3.0
    rta_recovery_cycles: int = 50


@dataclass(frozen=True)
class EnvironmentConfig:
    wind_ned_mps: tuple[float, float, float] = (0.0, 0.0, 0.0)
    air_density_kgm3: float = legacy.RHO_SL
    temperature_c: float = 15.0
    turbulence_std_mps: float = 0.0
