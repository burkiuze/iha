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
from .recorder import channel_events, load_log


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

    # ---- açıklanabilirlik ---------------------------------------------------
    def why_mode(self, target: str) -> list[dict[str, Any]]:
        """`target` moduna HER girişin gerekçesi; acil durum kararıysa kural bilgisi."""
        out = []
        for e in self.events_of(EventType.MODE_TRANSITION):
            d = e["data"]
            if d["target"] != target:
                continue
            cont = next((c["data"] for c in self.events_of(EventType.CONTINGENCY)
                         if c["time_s"] == e["time_s"] and c["data"].get("requested_mode") == target),
                        None)
            out.append({"time_s": e["time_s"], "from": d["source"], "reason": d["reason"],
                        "contingency_rule": None if cont is None else
                        {"priority": cont["priority"], "trigger": cont["trigger"],
                         "description": cont["reason"]}})
        return out

    def channel(self, name: str) -> list[dict[str, Any]]:
        """Uçuş veri kaydedicisinin mantıksal kanalı (bkz. `RECORDER_CHANNELS`)."""
        return list(self.snapshots) if name == "state" else channel_events(self.events, name)

    def why_rta_intervened(self) -> list[dict[str, Any]]:
        """Her RTA müdahalesi: tahmin edilen / mevcut ihlaller ve seçilen kaynak."""
        return [r for r in self.rta_history() if r["event"] != EventType.RTA_RECOVERY.value]

    def why_lane_isolated(self, lane: str) -> list[dict[str, Any]]:
        """Bir FCC şeridinin oylamadan çıkarılma (ISOLATED/FAILED) gerekçeleri."""
        return [{"time_s": e["time_s"], "lane": e["data"]["lane"], "state": e["data"]["state"],
                 "previous": e["data"]["previous"], "reason": e["data"]["reason"],
                 "configuration": e["data"].get("configuration"),
                 "voters": e["data"].get("voters")}
                for e in self.events_of(EventType.FCC_LANE_STATE_CHANGED)
                if e["data"]["lane"] == lane and e["data"]["state"] in ("isolated", "failed")]

    def why_nav_degraded(self) -> list[dict[str, Any]]:
        """Navigasyonun bozulduğu anlar: kaynak kaybı, dışlama, bütünlük kaybı."""
        out = [{"time_s": e["time_s"], "type": e["type"], "source": e["data"].get("source"),
                "reason": e["data"].get("reason")}
               for e in self.events_of(EventType.NAV_SOURCE_UNAVAILABLE,
                                       EventType.NAV_SOURCE_REJECTED, EventType.NAV_INTEGRITY_LOST)]
        return sorted(out, key=lambda x: x["time_s"])

    def why_actuator_removed(self, actuator: str) -> list[dict[str, Any]]:
        """Eyleyicinin nominal dağıtımdan çıkarılma nedeni + öncesindeki FDIR kararları."""
        excl = [e for e in self.events_of(EventType.ACTUATOR_EXCLUDED) if e["data"]["component"] == actuator]
        fdir = [{"time_s": e["time_s"], "type": e["type"], "state": e["data"].get("state"),
                 "reason": e["data"].get("reason")}
                for e in self.events_of(EventType.FDIR_WARNING, EventType.FDIR_FAILURE)
                if e["data"].get("component") == actuator]
        return [{"time_s": e["time_s"], "reason": e["data"]["reason"],
                 "hover_margin_after": e["data"].get("hover_margin_after"),
                 "monitor": e["data"].get("monitor"), "fdir_history": fdir} for e in excl]

    def why_command_rejected(self) -> list[dict[str, Any]]:
        return [{"time_s": e["time_s"], "category": e["data"].get("category"),
                 "stage": e["data"].get("stage"), "reasons": e["data"].get("reasons"),
                 "age_s": e["data"].get("age_s")}
                for e in self.events_of(EventType.COMMAND_REJECTED)]

    def nav_rejections(self) -> list[dict[str, Any]]:
        return [{"time_s": e["time_s"], "source": e["data"].get("source"),
                 "reason": e["data"].get("reason"),
                 "test_statistic": e["data"].get("test_statistic"),
                 "threshold": e["data"].get("threshold"),
                 "test_statistic_after": e["data"].get("test_statistic_after"),
                 "threshold_after": e["data"].get("threshold_after"),
                 "sources_used": e["data"].get("sources_used")}
                for e in self.events_of(EventType.NAV_SOURCE_REJECTED)]

    def nav_sources_at(self, t: float) -> list[str]:
        st = self.state_at(t)
        return [] if st is None else list(st.get("nav_used", []))

    def explain(self) -> dict[str, Any]:
        """Önemli kararların yapılandırılmış özeti (GCS / inceleme için)."""
        def pick(*types: EventType) -> list[dict[str, Any]]:
            return [{"time_s": e["time_s"], "type": e["type"],
                     "component": e["data"].get("component", ""),
                     "reason": e["data"].get("reason", e["message"])}
                    for e in self.events_of(*types)]
        return {
            "mission_outcome": self.metrics.get("mission_outcome_reason"),
            "mode_changes": [{"time_s": t, "from": a, "to": b, "reason": r}
                             for t, a, b, r in self.mode_history()],
            "contingencies": [{"time_s": e["time_s"], "trigger": e["data"]["trigger"],
                               "priority": e["data"]["priority"],
                               "requested_mode": e["data"]["requested_mode"]}
                              for e in self.events_of(EventType.CONTINGENCY)],
            "rta": self.rta_history(),
            "faults": [{"time_s": t, "event": typ, "fault_id": fid}
                       for t, typ, fid in self.fault_timeline()],
            "health": self.health_history(),
            "navigation": self.nav_rejections() + pick(EventType.NAV_SOURCE_UNAVAILABLE,
                                                       EventType.NAV_INTEGRITY_LOST,
                                                       EventType.NAV_INTEGRITY_RESTORED),
            "energy": [{"time_s": e["time_s"], **e["data"]}
                       for e in self.events_of(EventType.ENERGY_WARNING)],
            "transitions": pick(EventType.TRANSITION_COMPLETED, EventType.TRANSITION_ABORTED),
            "aborts": pick(EventType.MISSION_ABORT),
            "sensors": pick(EventType.SENSOR_DEGRADED, EventType.SENSOR_RESTORED,
                            EventType.SENSOR_HEALTH_CHANGED),
            "fcc": pick(EventType.FCC_LANE_STATE_CHANGED),
            "commands": self.why_command_rejected(),
            "allocation": pick(EventType.ACTUATOR_EXCLUDED),
            "vehicle_health": pick(EventType.VEHICLE_HEALTH_CHANGED),
        }

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
