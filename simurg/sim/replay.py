"""Kaydedilmiş simülasyonun yeniden analizi (tekrar oynatma oturumu).

İlk sürüm görsel arayüz içermez; Python API'si sağlar:
zaman çizelgesi, olaylar, durum geçmişi, mod/RTA/sağlık geçmişi.

    session = ReplaySession.from_source("kayit.json")   # ya da sözlük / sonuç
    session.state_at(42.0)
    session.rta_history()
"""

from __future__ import annotations

import bisect
from pathlib import Path
from typing import Any, Iterable

from ..core.events import EventType
from .recorder import load_log


class ReplaySession:
    def __init__(self, log: dict[str, Any]) -> None:
        self.log = load_log(log)
        self.meta: dict[str, Any] = self.log["meta"]
        self.events: list[dict[str, Any]] = sorted(self.log["events"], key=lambda e: e["seq"])
        self.snapshots: list[dict[str, Any]] = self.log["snapshots"]
        self.metrics: dict[str, Any] = self.log.get("metrics", {})
        self._snap_t = [s["t"] for s in self.snapshots]

    @classmethod
    def from_source(cls, source: str | Path | dict[str, Any] | Any) -> "ReplaySession":
        if hasattr(source, "log") and isinstance(source.log, dict):   # SimulationResult
            return cls(source.log)
        return cls(load_log(source))

    # ---- sorgular ---------------------------------------------------------
    def timeline(self) -> list[tuple[float, str, str]]:
        return [(e["time_s"], e["type"], e["message"]) for e in self.events]

    def events_of(self, *types: EventType | str) -> list[dict[str, Any]]:
        names = {t.value if isinstance(t, EventType) else t for t in types}
        return [e for e in self.events if e["type"] in names]

    def events_between(self, t0: float, t1: float) -> list[dict[str, Any]]:
        return [e for e in self.events if t0 <= e["time_s"] <= t1]

    def state_at(self, t: float) -> dict[str, Any] | None:
        """t anında ya da öncesindeki en son anlık görüntü."""
        i = bisect.bisect_right(self._snap_t, t + 1e-9) - 1
        return self.snapshots[i] if i >= 0 else None

    def series(self, key: str) -> list[tuple[float, Any]]:
        return [(s["t"], s.get(key)) for s in self.snapshots]

    def mode_history(self) -> list[tuple[float, str, str, str]]:
        return [(e["time_s"], e["data"]["source"], e["data"]["target"], e["data"]["reason"])
                for e in self.events_of(EventType.MODE_TRANSITION)]

    def rta_history(self) -> list[dict[str, Any]]:
        out = []
        for e in self.events_of(EventType.RTA_INTERVENTION, EventType.RTA_RECOVERY,
                                EventType.RTA_LATCHED):
            d = e["data"]
            out.append({"time_s": e["time_s"], "event": e["type"],
                        "selected_source": d.get("selected_source"),
                        "reasons": d.get("reasons", []),
                        "predicted_violations": d.get("predicted_violations", []),
                        "current_violations": d.get("current_violations", []),
                        "latched": d.get("latched", False)})
        return out

    def health_history(self) -> list[dict[str, Any]]:
        return [{"time_s": e["time_s"], "component_id": e["data"].get("component_id"),
                 "state": e["data"].get("state"), "health_score": e["data"].get("health_score"),
                 "reason": e["data"].get("reason")}
                for e in self.events_of(EventType.FDIR_WARNING, EventType.FDIR_FAILURE)]

    def fault_timeline(self) -> list[tuple[float, str, str]]:
        out = []
        for e in self.events_of(EventType.FAULT_INJECTED, EventType.FAULT_CLEARED):
            fid = e["data"]["fault"]["id"] if "fault" in e["data"] else e["data"].get("fault_id")
            out.append((e["time_s"], e["type"], fid))
        return out

    def ordering_is_consistent(self) -> bool:
        """Sıra numaraları kesin artan ve zaman damgaları azalmayan mı?"""
        seqs = [e["seq"] for e in self.log["events"]]
        times = [e["time_s"] for e in self.events]
        return seqs == sorted(seqs) and len(set(seqs)) == len(seqs) and \
            all(b >= a for a, b in zip(times, times[1:]))

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for e in self.events:
            counts[e["type"]] = counts.get(e["type"], 0) + 1
        return {"scenario": self.meta.get("name"), "seed": self.meta.get("seed"),
                "duration_s": self.metrics.get("duration_s"),
                "final_mode": self.metrics.get("final_mode"), "event_counts": counts}

    def __iter__(self) -> Iterable[dict[str, Any]]:
        return iter(self.events)
