"""Senaryo tanımı: başlangıç, süre, ortam, görev profili, arıza takvimi,
beklenen güvenlik sonuçları ve rastgele tohum.

Senaryo nesnesi değişmez (frozen) ve durumsuzdur; durumlu modeller
(ortam türbülansı, sensörler) motor tarafından her koşuda yeniden kurulur.
Böylece aynı senaryo + aynı tohum her zaman aynı sonucu üretir.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Callable

from ..core.config import EnvironmentConfig, SafetyConfig, SimulationConfig, VehicleConfig
from ..core.errors import InvalidScenarioError
from ..core.events import EventType
from .faults import FaultSchedule

if TYPE_CHECKING:
    from .engine import SimulationResult


@dataclass(frozen=True)
class MissionProfile:
    home_ne: tuple[float, float] = (0.0, 0.0)
    takeoff_alt_m: float = 50.0
    cruise_alt_m: float = 100.0
    cruise_speed_mps: float = 24.0
    waypoints: tuple[tuple[float, float], ...] = ((1200.0, 0.0), (1200.0, 900.0))
    waypoint_radius_m: float = 80.0
    back_transition_dist_m: float = 160.0
    departure_heading_deg: float = 0.0


@dataclass(frozen=True)
class InitialConditions:
    battery_soc: float = 0.80
    hydrogen_fraction: float = 1.0


@dataclass(frozen=True)
class Expectations:
    """Beklenen güvenlik sonuçları. Boş bırakılan alanlar denetlenmez."""
    required_events: tuple[EventType, ...] = ()
    forbidden_events: tuple[EventType, ...] = (EventType.IMPACT,)
    final_modes: tuple[str, ...] | None = None
    visited_modes: tuple[str, ...] = ()
    mission_completed: bool | None = None
    max_rta_interventions: int | None = None

    def evaluate(self, result: "SimulationResult") -> list[str]:
        failures = []
        types = {e["type"] for e in result.log["events"]}
        for ev in self.required_events:
            if ev.value not in types:
                failures.append(f"beklenen olay yok: {ev.value}")
        for ev in self.forbidden_events:
            if ev.value in types:
                failures.append(f"yasak olay gerçekleşti: {ev.value}")
        if self.final_modes is not None and result.final_state.flight_mode not in self.final_modes:
            failures.append(f"son mod {result.final_state.flight_mode}, beklenen {self.final_modes}")
        visited = {e["data"].get("target") for e in result.log["events"]
                   if e["type"] == EventType.MODE_TRANSITION.value}
        for m in self.visited_modes:
            if m not in visited:
                failures.append(f"moda hiç girilmedi: {m}")
        if self.mission_completed is not None and \
                result.metrics.mission_completed != self.mission_completed:
            failures.append(f"görev tamamlandı={result.metrics.mission_completed}, "
                            f"beklenen {self.mission_completed}")
        if self.max_rta_interventions is not None and \
                result.metrics.rta_interventions > self.max_rta_interventions:
            failures.append(f"RTA müdahalesi {result.metrics.rta_interventions} > "
                            f"{self.max_rta_interventions}")
        return failures


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str = ""
    duration_s: float = 300.0
    seed: int = 0
    mission: MissionProfile = field(default_factory=MissionProfile)
    initial: InitialConditions = field(default_factory=InitialConditions)
    faults: FaultSchedule = field(default_factory=FaultSchedule)
    expectations: Expectations = field(default_factory=Expectations)
    environment: EnvironmentConfig = field(default_factory=EnvironmentConfig)
    wind_keyframes: tuple[tuple[float, tuple[float, float, float]], ...] = ()
    vehicle: VehicleConfig = field(default_factory=VehicleConfig)
    sim: SimulationConfig = field(default_factory=SimulationConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    aero_factory: Callable[[], Any] | None = None
    tags: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.name:
            raise InvalidScenarioError("senaryo adı boş")
        if self.duration_s <= 0:
            raise InvalidScenarioError("süre pozitif olmalı")
        m = self.mission
        if m.takeoff_alt_m < 40.0:
            raise InvalidScenarioError("kalkış irtifası >= 40 m olmalı (geçiş koruma koşulu)")
        if m.cruise_alt_m < m.takeoff_alt_m:
            raise InvalidScenarioError("seyir irtifası kalkış irtifasından düşük olamaz")
        r = self.safety.geofence_radius_m
        for wp in m.waypoints:
            if math.hypot(wp[0] - m.home_ne[0], wp[1] - m.home_ne[1]) > r - 100.0:
                raise InvalidScenarioError(f"ara nokta geofence'e çok yakın/dışında: {wp}")
        if not 0.0 <= self.initial.battery_soc <= 1.0 or \
                not 0.0 <= self.initial.hydrogen_fraction <= 1.0:
            raise InvalidScenarioError("başlangıç enerji oranları 0..1 olmalı")

    def with_seed(self, seed: int) -> "Scenario":
        return replace(self, seed=int(seed))

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description,
                "duration_s": self.duration_s, "seed": self.seed,
                "faults": [f.to_dict() for f in self.faults],
                "wind_ned_mps": list(self.environment.wind_ned_mps),
                "turbulence_std_mps": self.environment.turbulence_std_mps,
                "waypoints": [list(w) for w in self.mission.waypoints],
                "dt_s": self.sim.dt_s, "integrator": self.sim.integrator,
                "tags": list(self.tags)}
