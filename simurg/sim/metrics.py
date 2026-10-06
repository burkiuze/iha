"""Simülasyon sonrası standart metrikler.

Metrikler iki kaynaktan hesaplanır:
  * `MetricsAccumulator`: motorun her adımda beslediği sayaçlar
    (doyma, zarf payı, enerji tüketimi, geçiş irtifa kaybı).
  * Kayıttaki olaylar: RTA müdahaleleri, mod geçişleri, arıza tespitleri.

Arıza "tespit edildi" sayılır, eğer etkinleşmesinden sonra hedef bileşenle
eşleşen bir tespit olayı yayınlanmışsa (`DETECTION_EVENTS` tablosu).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ..core.events import EventType

# arıza sistemi -> tespit sayılan olay türleri ve eşleşme anahtarı
DETECTION_EVENTS: dict[str, tuple[tuple[EventType, ...], str]] = {
    "actuator": ((EventType.FDIR_WARNING, EventType.FDIR_FAILURE), "component_id"),
    "sensor": ((EventType.NAV_SOURCE_REJECTED, EventType.NAV_SOURCE_UNAVAILABLE), "source"),
    "link": ((EventType.LINK_LOST,), ""),
    "controller": ((EventType.RTA_INTERVENTION,), ""),
    "energy": ((EventType.ENERGY_WARNING, EventType.TRANSITION_ABORTED), ""),
}


@dataclass
class MetricsAccumulator:
    ticks: int = 0
    saturated_ticks: int = 0
    fw_ticks: int = 0
    min_envelope_margin: float = float("inf")
    energy_consumed_j: float = 0.0
    max_transition_alt_loss_m: float = 0.0
    max_attitude_error_deg: float = 0.0
    min_altitude_airborne_m: float = float("inf")


@dataclass(frozen=True)
class SimulationMetrics:
    duration_s: float
    final_mode: str
    mission_completed: bool
    mission_outcome_reason: str
    impact: bool
    rta_interventions: int
    rta_latched: bool
    mode_transitions: int
    contingencies: int
    fault_count: int
    faults_detected: int
    detection_latency_s: dict[str, float] = field(default_factory=dict)
    max_detection_latency_s: float | None = None
    min_safety_margin: float | None = None
    energy_consumed_wh: float = 0.0
    remaining_usable_energy_wh: float = 0.0
    remaining_reserve_wh: float = 0.0
    nav_integrity_losses: int = 0
    nav_sources_rejected: int = 0
    actuator_saturation_pct: float = 0.0
    transitions_completed: int = 0
    transitions_aborted: int = 0
    max_transition_altitude_loss_m: float = 0.0
    max_attitude_error_deg: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _count(events: list[dict], t: EventType) -> int:
    return sum(1 for e in events if e["type"] == t.value)


def detection_latencies(events: list[dict], faults: list[dict],
                        activation: dict[str, float]) -> dict[str, float]:
    out: dict[str, float] = {}
    for f in faults:
        fid = f["id"]
        if fid not in activation:
            continue
        system, _, comp = f["target"].partition(":")
        types, key = DETECTION_EVENTS.get(system, ((), ""))
        t0 = activation[fid]
        for e in events:
            if e["time_s"] + 1e-9 < t0 or e["type"] not in {x.value for x in types}:
                continue
            if key and e["data"].get(key) != comp:
                continue
            out[fid] = round(e["time_s"] - t0, 6)
            break
    return out


def compute_metrics(events: list[dict], acc: MetricsAccumulator, duration_s: float,
                    final_mode: str, mission_completed: bool, faults: list[dict],
                    activation: dict[str, float], usable_wh: float,
                    reserve_wh: float, outcome_reason: str = "") -> SimulationMetrics:
    lat = detection_latencies(events, faults, activation)
    return SimulationMetrics(
        duration_s=round(duration_s, 6),
        final_mode=final_mode,
        mission_completed=mission_completed,
        mission_outcome_reason=outcome_reason,
        impact=_count(events, EventType.IMPACT) > 0,
        rta_interventions=_count(events, EventType.RTA_INTERVENTION),
        rta_latched=_count(events, EventType.RTA_LATCHED) > 0,
        mode_transitions=_count(events, EventType.MODE_TRANSITION),
        contingencies=_count(events, EventType.CONTINGENCY),
        fault_count=len(activation),
        faults_detected=len(lat),
        detection_latency_s=lat,
        max_detection_latency_s=max(lat.values()) if lat else None,
        min_safety_margin=None if acc.fw_ticks == 0 else round(acc.min_envelope_margin, 6),
        energy_consumed_wh=round(acc.energy_consumed_j / 3600.0, 6),
        remaining_usable_energy_wh=round(usable_wh, 6),
        remaining_reserve_wh=round(reserve_wh, 6),
        nav_integrity_losses=_count(events, EventType.NAV_INTEGRITY_LOST),
        nav_sources_rejected=_count(events, EventType.NAV_SOURCE_REJECTED),
        actuator_saturation_pct=round(100.0 * acc.saturated_ticks / max(acc.ticks, 1), 6),
        transitions_completed=_count(events, EventType.TRANSITION_COMPLETED),
        transitions_aborted=_count(events, EventType.TRANSITION_ABORTED),
        max_transition_altitude_loss_m=round(acc.max_transition_alt_loss_m, 6),
        max_attitude_error_deg=round(acc.max_attitude_error_deg, 6),
    )
