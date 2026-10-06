"""Yapılandırılmış uçuş kaydı ve kararlı JSON şeması.

Şema (sürüm 1):
{
  "schema": "simurg.sim-log",
  "schema_version": 1,
  "meta":      { senaryo tanımı, tohum, dt, aero kaynağı ... },
  "events":    [ {seq, time_s, type, source, message, data}, ... ]  (seq artan),
  "snapshots": [ {t, pos, vel, att_deg, rates, airspeed, groundspeed, alt, mode,
                  nav_ok, link_ok, health, soc, landed, extra...}, ... ],
  "metrics":   { SimulationMetrics alanları }
}

Her adımda tam durum yazılmaz; anlık görüntüler `snapshot_period_s`
aralıklarla, olaylar ise oluştukları anda (kayıpsız) kaydedilir.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from ..core.errors import SimulationError
from ..core.events import Event, EventBus

SCHEMA = "simurg.sim-log"
SCHEMA_VERSION = 1


def jsonable(x: Any) -> Any:
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, np.ndarray):
        return [jsonable(v) for v in x.tolist()]
    if isinstance(x, (np.floating, float)):
        f = float(x)
        return None if not math.isfinite(f) else f
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if hasattr(x, "value") and hasattr(x, "name"):     # Enum
        return x.value if isinstance(x.value, (str, int)) else x.name
    return x


class SimulationRecorder:
    def __init__(self, bus: EventBus, snapshot_period_s: float = 0.5,
                 meta: dict[str, Any] | None = None) -> None:
        self.snapshot_period_s = snapshot_period_s
        self.meta = jsonable(meta or {})
        self.events: list[dict[str, Any]] = []
        self.snapshots: list[dict[str, Any]] = []
        self.metrics: dict[str, Any] = {}
        self._next_snap = 0.0
        bus.subscribe(self._on_event)

    def _on_event(self, ev: Event) -> None:
        self.events.append(jsonable(ev.to_dict()))

    def maybe_snapshot(self, t: float, snap: dict[str, Any], force: bool = False) -> None:
        """Periyodik görüntü; `force` ile zorlanır. Zaman damgaları kesin artan kalır:
        aynı zamanlı ikinci görüntü öncekinin yerine geçer."""
        if force or t + 1e-9 >= self._next_snap:
            item = jsonable(snap)
            if self.snapshots and self.snapshots[-1].get("t") == item.get("t"):
                self.snapshots[-1] = item
            else:
                self.snapshots.append(item)
            self._next_snap = t + self.snapshot_period_s

    def finalize(self, metrics: dict[str, Any]) -> None:
        self.metrics = jsonable(metrics)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "schema_version": SCHEMA_VERSION, "meta": self.meta,
                "events": self.events, "snapshots": self.snapshots, "metrics": self.metrics}

    def to_json(self, path: str | Path | None = None, indent: int | None = None) -> str:
        text = json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, indent=indent)
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text


def load_log(source: str | Path | dict[str, Any]) -> dict[str, Any]:
    """JSON dosya yolu, JSON metni ya da sözlükten kayıt yükler ve şemayı denetler."""
    if isinstance(source, dict):
        d = source
    else:
        text = str(source)
        if not text.lstrip().startswith("{"):
            text = Path(source).read_text(encoding="utf-8")
        d = json.loads(text)
    if d.get("schema") != SCHEMA:
        raise SimulationError(f"tanınmayan kayıt şeması: {d.get('schema')}")
    if d.get("schema_version") != SCHEMA_VERSION:
        raise SimulationError(f"desteklenmeyen şema sürümü: {d.get('schema_version')}")
    return d
