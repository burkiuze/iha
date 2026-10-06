"""Hafif, senkron ve deterministik olay yolu (event bus).

Modüller birbirini doğrudan çağırmak yerine olay yayınlar; kayıt (recorder),
metrikler ve GCS gibi tüketiciler abone olur. Bilinçli kısıtlar:

* Senkron: `publish` döndüğünde tüm aboneler çalışmıştır (determinizm).
* Aboneler kayıt sırasına göre çağrılır.
* Her olay artan bir sıra numarası (`seq`) alır; tekrar oynatmada sıralama
  bu numarayla korunur.
* Abone içinde oluşan hata yutulmaz; yukarı fırlatılır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class EventType(str, Enum):
    SIM_STARTED = "sim_started"
    SIM_FINISHED = "sim_finished"
    SIM_FAILED = "sim_failed"                  # sayısal/mantıksal hata (yeniden fırlatılır)
    SENSOR_DEGRADED = "sensor_degraded"        # ölçüm yok -> açık geri dönüş kaynağı
    SENSOR_RESTORED = "sensor_restored"
    FAULT_INJECTED = "fault_injected"
    FAULT_CLEARED = "fault_cleared"
    MODE_TRANSITION = "mode_transition"
    MODE_REJECTED = "mode_rejected"
    CONTINGENCY = "contingency"
    RTA_INTERVENTION = "rta_intervention"
    RTA_RECOVERY = "rta_recovery"
    RTA_LATCHED = "rta_latched"
    FDIR_WARNING = "fdir_warning"          # bileşen DEGRADED
    FDIR_FAILURE = "fdir_failure"          # bileşen FAILED
    NAV_SOURCE_REJECTED = "nav_source_rejected"      # tutarsız -> dışlandı
    NAV_SOURCE_UNAVAILABLE = "nav_source_unavailable"  # ölçüm yok
    NAV_INTEGRITY_LOST = "nav_integrity_lost"
    NAV_INTEGRITY_RESTORED = "nav_integrity_restored"
    LINK_LOST = "link_lost"
    LINK_RESTORED = "link_restored"
    ENERGY_WARNING = "energy_warning"
    TRANSITION_STARTED = "transition_started"
    TRANSITION_COMPLETED = "transition_completed"
    TRANSITION_ABORTED = "transition_aborted"
    MISSION_ABORT = "mission_abort"
    MISSION_COMPLETE = "mission_complete"
    TOUCHDOWN = "touchdown"
    IMPACT = "impact"


@dataclass(frozen=True)
class Event:
    type: EventType
    time_s: float
    source: str
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    seq: int = -1

    def to_dict(self) -> dict[str, Any]:
        return {"seq": self.seq, "time_s": round(self.time_s, 6), "type": self.type.value,
                "source": self.source, "message": self.message, "data": self.data}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Event":
        return Event(EventType(d["type"]), float(d["time_s"]), d["source"],
                     d.get("message", ""), dict(d.get("data", {})), int(d["seq"]))


Handler = Callable[[Event], None]


class EventBus:
    def __init__(self) -> None:
        self._subs: list[tuple[frozenset[EventType] | None, Handler]] = []
        self._seq = 0

    def subscribe(self, handler: Handler,
                  types: EventType | set[EventType] | None = None) -> None:
        """`types=None` tüm olaylara abone olur."""
        if isinstance(types, EventType):
            types = {types}
        self._subs.append((frozenset(types) if types is not None else None, handler))

    def publish(self, type: EventType, time_s: float, source: str,
                message: str = "", /, **data: Any) -> Event:
        ev = Event(type, float(time_s), source, message, data, self._seq)
        self._seq += 1
        for filt, handler in self._subs:
            if filt is None or type in filt:
                handler(ev)
        return ev


class EventLog:
    """Basit abone: tüm olayları sırayla tutar."""

    def __init__(self, bus: EventBus | None = None) -> None:
        self.events: list[Event] = []
        if bus is not None:
            bus.subscribe(self.events.append)

    def of_type(self, *types: EventType) -> list[Event]:
        return [e for e in self.events if e.type in types]
