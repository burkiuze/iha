"""Sensör ölçüm hattı: ham ölçüm -> meta verili, sağlık bilgili ölçüm.

Her sensör kanalı aynı sabit zinciri uygular:

    Sensor Driver (ham SensorMeasurement)
      -> Timestamp       zaman damgası denetimi + tazelik (freshness)
      -> Signal Valid.   geçerlilik bayrağı, sonluluk, boyut
      -> Plausibility    fiziksel aralık + değişim hızı sınırı
      -> Sensor Health   kalıcılık sayaçlı NOMINAL/DEGRADED/FAILED/UNKNOWN
      -> Measurement Bus son ölçüm + sağlık özeti (kaynak bazında)

Her `Measurement` şu meta veriyi taşır: kaynak, zaman damgası, geçerlilik,
tazelik, kalite, sağlık, güven (+ gerekçeler).

Fail-safe: hiç ölçüm üretmemiş kanal UNKNOWN'dır (NOMINAL değil); bayat ya
da akla yatkın olmayan ölçüm `usable=False` döner ve güveni sıfırdır.

Kapsam: yazılım düzeyinde simülasyon soyutlaması. Gerçek sensör sürücüsü,
kalibrasyon ya da donanım arayüzü içermez. Hat yalnızca GÖZLEMLER; ölçümü
değiştirmez ve RNG tüketmez (simülasyon determinizmi etkilenmez).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

from ..core.types import HealthState, SensorMeasurement

STAGES = ("timestamp", "signal_validation", "plausibility", "sensor_health", "measurement_bus")


class Validity(str, Enum):
    VALID = "valid"
    INVALID = "invalid"          # sensör geçersiz bildirdi ya da sonlu değil
    STALE = "stale"              # tazelik sınırı aşıldı / zaman damgası tutarsız
    IMPLAUSIBLE = "implausible"  # fiziksel aralık ya da değişim hızı dışında


@dataclass(frozen=True)
class Measurement:
    source: str
    timestamp: float
    value: np.ndarray
    covariance: np.ndarray
    validity: Validity
    freshness_s: float
    quality: float               # 0..1, sensörün beyanı
    health: HealthState          # kanalın kalıcılık sonrası sağlığı
    confidence: float            # 0..1, kullanılabilirlik ağırlığı
    reasons: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        return self.validity is Validity.VALID and self.health in (HealthState.NOMINAL,
                                                                   HealthState.DEGRADED)

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "timestamp": round(self.timestamp, 6),
                "validity": self.validity.value, "freshness_s": round(self.freshness_s, 6),
                "quality": round(self.quality, 6), "health": self.health.value,
                "confidence": round(self.confidence, 6), "reasons": list(self.reasons)}


@dataclass(frozen=True)
class ChannelSpec:
    """Kanal sınırları (yazılım akla yatkınlık sınırları; kalibrasyon değildir)."""
    lower: float = -math.inf
    upper: float = math.inf
    max_rate_per_s: float = math.inf
    max_age_s: float = 0.5
    fail_after: int = 5          # ardışık kötü ölçüm -> FAILED
    recover_after: int = 5       # ardışık iyi ölçüm -> NOMINAL


@dataclass(frozen=True)
class HealthChange:
    source: str
    previous: HealthState
    state: HealthState
    reason: str


@dataclass
class SensorChannel:
    source: str
    spec: ChannelSpec = field(default_factory=ChannelSpec)

    def __post_init__(self) -> None:
        self.health = HealthState.UNKNOWN
        self.last_valid: Measurement | None = None
        self.last_reason = "olcum_yok"
        self._bad = 0
        self._good = 0

    def process(self, raw: SensorMeasurement, now: float) -> tuple[Measurement, HealthChange | None]:
        reasons: list[str] = []
        sp = self.spec
        # 1. timestamp
        freshness = now - raw.timestamp
        validity = Validity.VALID
        if not math.isfinite(raw.timestamp) or freshness < -1e-9:
            validity, reasons = Validity.STALE, ["zaman_damgasi_tutarsiz"]
        elif freshness > sp.max_age_s:
            validity, reasons = Validity.STALE, ["bayat_olcum"]
        # 2. signal validation
        value = np.atleast_1d(np.asarray(raw.value, float))
        if validity is Validity.VALID:
            if not raw.valid:
                validity, reasons = Validity.INVALID, ["sensor_gecersiz_bildirdi"]
            elif not np.all(np.isfinite(value)):
                validity, reasons = Validity.INVALID, ["sonlu_degil"]
        # 3. plausibility
        if validity is Validity.VALID:
            if np.any(value < sp.lower) or np.any(value > sp.upper):
                validity, reasons = Validity.IMPLAUSIBLE, ["fiziksel_aralik_disi"]
            elif self.last_valid is not None and math.isfinite(sp.max_rate_per_s):
                dt = raw.timestamp - self.last_valid.timestamp
                if dt > 1e-9 and np.max(np.abs(value - self.last_valid.value)) / dt > sp.max_rate_per_s:
                    validity, reasons = Validity.IMPLAUSIBLE, ["degisim_hizi_sinir_disi"]
        # 4. sensor health (kalıcılık)
        change = self._update_health(validity, raw.health, reasons)
        ok = validity is Validity.VALID
        conf = float(np.clip(raw.quality * raw.health, 0.0, 1.0)) if ok else 0.0
        m = Measurement(self.source, raw.timestamp, value, np.asarray(raw.covariance, float),
                        validity, max(freshness, 0.0), float(raw.quality), self.health, conf,
                        tuple(reasons))
        if ok:
            self.last_valid = m
        return m, change

    def _update_health(self, validity: Validity, declared: float,
                       reasons: list[str]) -> HealthChange | None:
        prev = self.health
        if validity is Validity.VALID:
            self._good, self._bad = self._good + 1, 0
            if prev in (HealthState.UNKNOWN,) or (prev is not HealthState.NOMINAL
                                                  and self._good >= self.spec.recover_after):
                self.health = HealthState.NOMINAL if declared >= 1.0 else HealthState.DEGRADED
            elif prev is HealthState.NOMINAL and declared < 1.0:
                self.health = HealthState.DEGRADED
            reason = "olcum_gecerli" if self.health is HealthState.NOMINAL else "beyan_edilen_saglik_dusuk"
        else:
            self._bad, self._good = self._bad + 1, 0
            if self._bad >= self.spec.fail_after:
                self.health = HealthState.FAILED
            elif prev is HealthState.NOMINAL:
                self.health = HealthState.DEGRADED
            reason = reasons[0]
        self.last_reason = reason
        return None if self.health is prev else HealthChange(self.source, prev, self.health, reason)


class MeasurementBus:
    """Kaynak bazında son ölçüm ve sağlık özeti (mantıksal ölçüm yolu)."""

    def __init__(self) -> None:
        self._latest: dict[str, Measurement] = {}

    def publish(self, m: Measurement) -> None:
        self._latest[m.source] = m

    def latest(self, source: str) -> Measurement | None:
        return self._latest.get(source)

    def sources(self) -> tuple[str, ...]:
        return tuple(sorted(self._latest))


class SensorPipeline:
    """Tüm kanalları yönetir; ham ölçümleri hattan geçirip ölçüm yoluna yazar."""

    def __init__(self, specs: dict[str, ChannelSpec]) -> None:
        self.channels = {sid: SensorChannel(sid, spec) for sid, spec in specs.items()}
        self.bus = MeasurementBus()

    def process(self, raw: SensorMeasurement, now: float) -> HealthChange | None:
        ch = self.channels.get(raw.sensor_id)
        if ch is None:
            return None                  # kayıtlı olmayan kaynak yok sayılmaz: kanal açılmaz
        m, change = ch.process(raw, now)
        self.bus.publish(m)
        return change

    def check_freshness(self, now: float) -> list[HealthChange]:
        """Ölçüm gelmeyen kanallar: son ölçüm bayatsa sağlık düşer (sessiz kayıp yok)."""
        out = []
        for ch in self.channels.values():
            last = self.bus.latest(ch.source)
            if last is not None and now - last.timestamp > ch.spec.max_age_s:
                stale = SensorMeasurement(ch.source, last.timestamp, last.value, last.covariance,
                                          False, 0.0, 0.0)
                m, change = ch.process(stale, now)
                self.bus.publish(m)
                if change is not None:
                    out.append(change)
        return out

    def health(self) -> dict[str, HealthState]:
        return {sid: ch.health for sid, ch in sorted(self.channels.items())}

    def reasons(self) -> dict[str, str]:
        return {sid: ch.last_reason for sid, ch in sorted(self.channels.items())}
