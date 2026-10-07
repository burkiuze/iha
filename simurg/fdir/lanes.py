"""Üçlü uçuş bilgisayarı şerit yönetimi: karşılaştırıcı, oylayıcı, yalıtım.

    Lane A ─┐
    Lane B ─┼─> Watchdog -> Cross-Lane Comparator -> Lane Voter -> çıktı
    Lane C ─┘                       │
                                    └──> Lane Isolation Manager (durumlar)

Şerit durumları:
  UNKNOWN   ilk çıktıdan önce (çalıştığı varsayılmaz)
  NOMINAL   oylamaya katılır, uyuşuyor
  DEGRADED  geçici uyuşmazlık ya da tek çevrim kalp atışı kaybı (hâlâ izleniyor)
  ISOLATED  kalıcı çapraz-karşılaştırma uyuşmazlığı -> oylamadan ÇIKARILIR
  FAILED    kalp atışı / bekçi köpeği zaman aşımı ya da sonlu olmayan çıktı

ISOLATED ve FAILED uçuş içinde kalıcıdır (mandallı): bir şerit oylayıcıya
nominal şerit olarak geri DÖNMEZ. Tek bir şerit arızası çıktıyı bozmaz:
üç şeritte medyan, iki şeritte uyuşma denetimi, uyuşmazlıkta son oylanmış
çıktıya en yakın şerit seçilir ve durum DEGRADED raporlanır.

Bu modül simülasyon soyutlamasıdır; gerçek şerit senkronizasyonu, veri
yolu ya da donanım arayüzü içermez.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

LANES = ("A", "B", "C")


class LaneState(str, Enum):
    NOMINAL = "nominal"
    DEGRADED = "degraded"
    ISOLATED = "isolated"
    FAILED = "failed"
    UNKNOWN = "unknown"


EXCLUDED = frozenset({LaneState.ISOLATED, LaneState.FAILED})


@dataclass(frozen=True)
class LaneOutput:
    lane: str
    value: np.ndarray | None
    timestamp: float
    heartbeat: bool = True


@dataclass(frozen=True)
class LaneChange:
    lane: str
    previous: LaneState
    state: LaneState
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"lane": self.lane, "previous": self.previous.value, "state": self.state.value,
                "reason": self.reason}


@dataclass(frozen=True)
class VoteResult:
    output: np.ndarray | None
    voters: tuple[str, ...]
    configuration: str             # triplex / duplex / simplex / none
    disagreement: bool
    states: dict[str, LaneState]
    changes: tuple[LaneChange, ...]


@dataclass
class TriplexVoter:
    tol: float = 0.05              # normalize eyleyici komutu
    persistence: int = 5           # ardışık uyuşmazlık -> ISOLATED
    heartbeat_timeout: int = 3     # ardışık kayıp kalp atışı -> FAILED

    def __post_init__(self) -> None:
        self.states = {l: LaneState.UNKNOWN for l in LANES}
        self.reasons = {l: "cikti_yok" for l in LANES}
        self._miss = {l: 0 for l in LANES}
        self._mis = {l: 0 for l in LANES}

    def _set(self, lane: str, st: LaneState, reason: str, out: list[LaneChange]) -> None:
        if self.states[lane] is st:
            return
        if self.states[lane] in EXCLUDED:          # mandallı: geri dönüş yok
            return
        out.append(LaneChange(lane, self.states[lane], st, reason))
        self.states[lane], self.reasons[lane] = st, reason

    def vote(self, outputs: list[LaneOutput], last: np.ndarray | None) -> VoteResult:
        changes: list[LaneChange] = []
        vals: dict[str, np.ndarray] = {}
        # 1. bekçi köpeği / kalp atışı
        for o in outputs:
            if self.states[o.lane] in EXCLUDED:
                continue
            ok = o.heartbeat and o.value is not None and bool(np.all(np.isfinite(o.value)))
            if not ok:
                self._miss[o.lane] += 1
                why = "sonlu_olmayan_cikti" if o.heartbeat and o.value is not None \
                    else "kalp_atisi_yok"
                if self._miss[o.lane] >= self.heartbeat_timeout:
                    self._set(o.lane, LaneState.FAILED, f"bekci_zaman_asimi:{why}", changes)
                else:
                    self._set(o.lane, LaneState.DEGRADED, why, changes)
                continue
            self._miss[o.lane] = 0
            vals[o.lane] = np.asarray(o.value, float)
        active = [l for l in LANES if l in vals]
        # 2. karşılaştırma + oylama
        disagreement = False
        if len(active) == 3:
            out = np.median(np.array([vals[l] for l in active]), axis=0)
            for l in active:
                if float(np.max(np.abs(vals[l] - out))) > self.tol:
                    self._mis[l] += 1
                    if self._mis[l] >= self.persistence:
                        self._set(l, LaneState.ISOLATED, "capraz_karsilastirma_uyusmazligi", changes)
                    else:
                        self._set(l, LaneState.DEGRADED, "gecici_uyusmazlik", changes)
                else:
                    self._mis[l] = 0
                    self._set(l, LaneState.NOMINAL, "uyusuyor", changes)
            conf = "triplex"
        elif len(active) == 2:
            a, b = active
            if float(np.max(np.abs(vals[a] - vals[b]))) <= self.tol:
                out = 0.5 * (vals[a] + vals[b])
                for l in active:
                    self._mis[l] = 0
                    self._set(l, LaneState.NOMINAL, "ikili_uyusuyor", changes)
            else:
                # Hakem yok: son oylanmış çıktıya en yakın şerit; uzak olan kalıcıysa yalıtılır.
                disagreement = True
                ref = last if last is not None else 0.5 * (vals[a] + vals[b])
                near, far = sorted(active, key=lambda l: float(np.max(np.abs(vals[l] - ref))))
                out = vals[near]
                self._mis[far] += 1
                if self._mis[far] >= self.persistence:
                    self._set(far, LaneState.ISOLATED, "ikili_uyusmazlik_son_cikti_hakem", changes)
                else:
                    self._set(far, LaneState.DEGRADED, "ikili_uyusmazlik", changes)
                self._set(near, LaneState.DEGRADED, "ikili_uyusmazlik", changes)
            conf = "duplex"
        elif len(active) == 1:
            out = vals[active[0]]
            conf = "simplex"
        else:
            out = None
            conf = "none"
        voters = tuple(l for l in active if self.states[l] not in EXCLUDED)
        return VoteResult(out, voters, conf, disagreement, dict(self.states), tuple(changes))

    @property
    def available(self) -> tuple[str, ...]:
        return tuple(l for l in LANES if self.states[l] not in EXCLUDED)
