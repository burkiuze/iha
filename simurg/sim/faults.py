"""Zaman tabanlı arıza enjeksiyonu çerçevesi.

    Fault          : tanım (id, tür, hedef, başlangıç, süre, şiddet, açıklama)
    FaultSchedule  : doğrulanmış, sıralı arıza listesi
    FaultInjector  : simülasyon zamanında arızaları etkinleştirir/temizler
    FaultTarget    : arızayı uygulayan alt sistem arayüzü (Protocol)

Hedef adlandırma: "<sistem>:<bileşen>" — örn. "actuator:M2U", "sensor:GNSS",
"link:c2", "energy:fuel_cell", "controller:advanced".

Arızalar yalnızca simülasyondaki modelleri bozar (yazılım doğrulaması için);
gerçek donanıma uygulanacak bir mekanizma içermez.

Determinizm: arıza, zamanı `start_time_s`'e eşit ya da onu geçen İLK adımda
etkinleşir; aynı senaryo + dt her koşuda aynı adımı seçer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from ..core.errors import InvalidScenarioError
from ..core.events import EventBus, EventType


class FaultKind(str, Enum):
    SENSOR_DROPOUT = "sensor_dropout"
    SENSOR_BIAS = "sensor_bias"
    SENSOR_NOISE = "sensor_noise"
    ACTUATOR_DEGRADED = "actuator_degraded"
    ACTUATOR_STUCK = "actuator_stuck"
    ACTUATOR_OFFLINE = "actuator_offline"
    LINK_LOSS = "link_loss"
    ENERGY_FC_DEGRADED = "energy_fc_degraded"
    ENERGY_BATTERY_FADE = "energy_battery_fade"
    ENERGY_POWER_LIMIT = "energy_power_limit"
    CONTROLLER_FAULT = "controller_fault"     # gelişmiş kontrolcü hatalı öneri üretir


_SYSTEM_OF_KIND = {
    FaultKind.SENSOR_DROPOUT: "sensor", FaultKind.SENSOR_BIAS: "sensor",
    FaultKind.SENSOR_NOISE: "sensor", FaultKind.ACTUATOR_DEGRADED: "actuator",
    FaultKind.ACTUATOR_STUCK: "actuator", FaultKind.ACTUATOR_OFFLINE: "actuator",
    FaultKind.LINK_LOSS: "link", FaultKind.ENERGY_FC_DEGRADED: "energy",
    FaultKind.ENERGY_BATTERY_FADE: "energy", FaultKind.ENERGY_POWER_LIMIT: "energy",
    FaultKind.CONTROLLER_FAULT: "controller",
}


@dataclass(frozen=True)
class Fault:
    id: str
    kind: FaultKind
    target: str
    start_time_s: float
    duration_s: float | None = None      # None: kalıcı
    severity: float = 1.0                # 0..1 (türüne göre anlamı değişir)
    description: str = ""
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def system(self) -> str:
        return self.target.split(":", 1)[0]

    @property
    def component(self) -> str:
        return self.target.split(":", 1)[1] if ":" in self.target else ""

    @property
    def end_time_s(self) -> float | None:
        return None if self.duration_s is None else self.start_time_s + self.duration_s

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind.value, "target": self.target,
                "start_time_s": self.start_time_s, "duration_s": self.duration_s,
                "severity": self.severity, "description": self.description,
                "params": dict(self.params)}

    def validate(self) -> None:
        if not self.id:
            raise InvalidScenarioError("arıza kimliği boş olamaz")
        if self.start_time_s < 0:
            raise InvalidScenarioError(f"{self.id}: başlangıç negatif olamaz")
        if self.duration_s is not None and self.duration_s <= 0:
            raise InvalidScenarioError(f"{self.id}: süre pozitif olmalı")
        if not 0.0 <= self.severity <= 1.0:
            raise InvalidScenarioError(f"{self.id}: şiddet 0..1 olmalı")
        if self.system != _SYSTEM_OF_KIND[self.kind]:
            raise InvalidScenarioError(
                f"{self.id}: {self.kind.value} türü '{_SYSTEM_OF_KIND[self.kind]}' "
                f"sistemini hedeflemeli, '{self.system}' verildi")


@dataclass(frozen=True)
class FaultSchedule:
    faults: tuple[Fault, ...] = ()

    def __post_init__(self) -> None:
        ids = [f.id for f in self.faults]
        if len(ids) != len(set(ids)):
            raise InvalidScenarioError("arıza kimlikleri benzersiz olmalı")
        for f in self.faults:
            f.validate()
        object.__setattr__(self, "faults",
                           tuple(sorted(self.faults, key=lambda f: (f.start_time_s, f.id))))

    def __iter__(self):
        return iter(self.faults)

    def __len__(self) -> int:
        return len(self.faults)


class FaultTarget(Protocol):
    def apply_fault(self, fault: Fault) -> None: ...

    def clear_fault(self, fault: Fault) -> None: ...


class FaultInjector:
    def __init__(self, schedule: FaultSchedule, targets: dict[str, FaultTarget],
                 bus: EventBus | None = None) -> None:
        missing = {f.system for f in schedule} - set(targets)
        if missing:
            raise InvalidScenarioError(f"arıza hedef sistemi yok: {sorted(missing)}")
        self.schedule = schedule
        self.targets = targets
        self.bus = bus
        self.active: dict[str, Fault] = {}
        self.activation_times: dict[str, float] = {}
        self.cleared: set[str] = set()

    def update(self, t: float, eps: float = 1e-9) -> None:
        for f in self.schedule:
            if f.id in self.active or f.id in self.cleared:
                continue
            if t + eps >= f.start_time_s:
                self.targets[f.system].apply_fault(f)
                self.active[f.id] = f
                self.activation_times[f.id] = t
                if self.bus:
                    self.bus.publish(EventType.FAULT_INJECTED, t, "fault_injector",
                                     f.description or f.kind.value, fault=f.to_dict())
        for fid in list(self.active):
            f = self.active[fid]
            if f.end_time_s is not None and t + eps >= f.end_time_s:
                self.targets[f.system].clear_fault(f)
                del self.active[fid]
                self.cleared.add(fid)
                if self.bus:
                    self.bus.publish(EventType.FAULT_CLEARED, t, "fault_injector",
                                     f.kind.value, fault_id=fid, target=f.target)


class EnergyFaultTarget:
    """Enerji yöneticisinin bozunum katsayılarını arızaya göre ayarlar."""

    _ATTR = {FaultKind.ENERGY_FC_DEGRADED: "fc_power_scale",
             FaultKind.ENERGY_BATTERY_FADE: "batt_capacity_scale",
             FaultKind.ENERGY_POWER_LIMIT: "batt_discharge_scale"}

    def __init__(self, manager: Any) -> None:
        self.em = manager

    def apply_fault(self, fault: Fault) -> None:
        setattr(self.em, self._ATTR[fault.kind], 1.0 - fault.severity)
        if fault.kind is FaultKind.ENERGY_POWER_LIMIT:     # DC bara akım sınırı
            self.em.sc_power_scale = 1.0 - fault.severity

    def clear_fault(self, fault: Fault) -> None:
        if fault.kind is not FaultKind.ENERGY_BATTERY_FADE:   # kapasite kaybı kalıcı
            setattr(self.em, self._ATTR[fault.kind], 1.0)
        if fault.kind is FaultKind.ENERGY_POWER_LIMIT:
            self.em.sc_power_scale = 1.0


class ControllerFaultTarget:
    """Gelişmiş kontrolcünün hatalı (zarf dışı) öneri üretmesini taklit eder.

    Amaç RTA'nın koruyucu davranışını doğrulamaktır; şiddet 1.0 -> 75° yatış.
    """

    def __init__(self, guidance: Any) -> None:
        self.g = guidance

    def apply_fault(self, fault: Fault) -> None:
        self.g.fault_bank_deg = float(fault.params.get("bank_deg", 75.0 * fault.severity))

    def clear_fault(self, fault: Fault) -> None:
        self.g.fault_bank_deg = None
