"""Komuta-kontrol (C2) bağlantı modeli (simülasyon)."""

from __future__ import annotations

from .faults import Fault


class LinkModel:
    def __init__(self) -> None:
        self.up = True
        self.lost_since: float | None = None
        self._down_faults: set[str] = set()

    def update(self, t: float) -> tuple[bool, float]:
        """(bağlantı var mı, kesinti süresi s)."""
        up = not self._down_faults
        if up:
            self.lost_since = None
        elif self.lost_since is None:
            self.lost_since = t
        self.up = up
        return up, 0.0 if up else t - self.lost_since

    def apply_fault(self, fault: Fault) -> None:
        self._down_faults.add(fault.id)

    def clear_fault(self, fault: Fault) -> None:
        self._down_faults.discard(fault.id)
