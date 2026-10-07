"""Üçlü uçuş kontrol bilgisayarının simülasyon soyutlaması.

Simülasyonda her şerit aynı (deterministik) kontrol + dağıtım hesabının bir
KOPYASINI çıktı önerisi olarak verir; şeritlere özgü arızalar (kalp atışı
kaybı, çıktı sapması) arıza enjeksiyonuyla eklenir. Çıktı `TriplexVoter`
üzerinden geçer ve eyleyicilere yalnızca oylanmış komut gider.

Sınırlama (dürüst durum): şeritler farklı mimarili bağımsız uygulamalar
DEĞİLDİR; ortak mod (common-mode) yazılım hatası bu modelle gösterilemez.
Arıza hedefi: "fcc:A", "fcc:B", "fcc:C".
"""

from __future__ import annotations

import numpy as np

from ..core.errors import InvalidScenarioError
from ..fdir.lanes import LANES, LaneOutput, TriplexVoter, VoteResult
from .faults import Fault, FaultKind


class TriplexFlightComputer:
    def __init__(self, voter: TriplexVoter | None = None) -> None:
        self.voter = voter or TriplexVoter()
        self._down: dict[str, set[str]] = {l: set() for l in LANES}
        self._offset: dict[str, dict[str, float]] = {l: {} for l in LANES}
        self.last_output: np.ndarray | None = None
        self.last: VoteResult | None = None

    def heartbeat_ok(self, lane: str) -> bool:
        return not self._down[lane]

    def lane_outputs(self, u: np.ndarray, t: float) -> list[LaneOutput]:
        out = []
        for l in LANES:
            if self._down[l]:
                out.append(LaneOutput(l, None, t, heartbeat=False))
            else:
                off = sum(self._offset[l].values())
                out.append(LaneOutput(l, u + off if off else u.copy(), t))
        return out

    def step(self, u: np.ndarray, t: float) -> VoteResult:
        res = self.voter.vote(self.lane_outputs(np.asarray(u, float), t), self.last_output)
        if res.output is not None:
            self.last_output = res.output
        self.last = res
        return res

    @property
    def has_output(self) -> bool:
        return self.last is None or self.last.output is not None

    # ---- FaultTarget --------------------------------------------------------
    def _lane(self, fault: Fault) -> str:
        if fault.component not in LANES:
            raise InvalidScenarioError(f"bilinmeyen FCC şeridi: {fault.component}")
        return fault.component

    def apply_fault(self, fault: Fault) -> None:
        l = self._lane(fault)
        if fault.kind is FaultKind.FCC_LANE_UNAVAILABLE:
            self._down[l].add(fault.id)
        elif fault.kind is FaultKind.FCC_LANE_DIVERGENCE:
            self._offset[l][fault.id] = float(fault.params.get("offset", 0.3 * fault.severity))
        else:
            raise InvalidScenarioError(f"FCC bu arızayı desteklemiyor: {fault.kind}")

    def clear_fault(self, fault: Fault) -> None:
        l = self._lane(fault)
        self._down[l].discard(fault.id)
        self._offset[l].pop(fault.id, None)
