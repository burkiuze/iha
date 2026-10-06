"""Çalışma zamanı güvencesi (Runtime Assurance, Simplex mimarisi).

Karmaşık / öğrenen "gelişmiş kontrolcü" (AC) ile basit, doğrulanabilir
"güvenlik kontrolcüsü" (SC) arasında anahtarlama yapar. Karar mantığı
kasıtlı olarak küçük tutulmuştur; bu modülün kendisi DAL-B seviyesinde
geliştirilip biçimsel olarak doğrulanacak çekirdektir.

Kurallar:
  1. Mevcut durum SERT zarfın dışındaysa -> SC, kilitli (uçuş sonuna dek).
  2. AC komutu uygulanırsa ufuk (lookahead) sonunda durum YUMUŞAK zarfın
     dışına taşacaksa -> SC.
  3. SC aktifken, durum yumuşak zarfın içinde ek bir pay ile
     `recovery_cycles` ardışık çevrim kalırsa -> AC'ye geri dönülür
     (histerezis; titreşimli anahtarlamayı önler).

Modüler yapı:
  StatePredictor (Protocol)  -> KinematicPredictor (varsayılan, `predict`)
  SafetyEnvelope (= Envelope) -> ihlal listesi
  RuntimeAssurance.decide()  -> SafetyDecision (açıklanabilir meta veri)
  RuntimeAssurance.select()  -> (Command, Source)  [geriye dönük uyumlu]

Kapsam: zarf sabit kanat rejimi için tanımlıdır (seyir, görev, dönüş,
bekleme). Askı ve geçişte RTA devrede değildir; bu fazların güvenliği
geçiş koordinatörünün iptal mantığı ve acil durum yöneticisiyle sağlanır.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class Source(Enum):
    ADVANCED = "advanced"
    SAFETY = "safety"


@dataclass
class EnvelopeState:
    """RTA'nın gördüğü durum görünümü (merkezi `core.types.VehicleState`'ten türetilir)."""
    alt_agl_m: float
    airspeed_mps: float
    bank_deg: float
    pitch_deg: float
    climb_mps: float
    fence_dist_m: float          # en yakın geofence sınırına uzaklık (içeride +)
    fence_closing_mps: float     # sınıra yaklaşma hızı (+ yaklaşıyor)

    @classmethod
    def from_vehicle_state(cls, vs: Any, fence_dist_m: float,
                           fence_closing_mps: float) -> "EnvelopeState":
        """`simurg.core.types.VehicleState` -> RTA görünümü (düz arazi: AGL = irtifa)."""
        _, pitch, bank = vs.attitude_deg
        return cls(vs.altitude_m, vs.airspeed_mps, bank, pitch, vs.climb_mps,
                   fence_dist_m, fence_closing_mps)


# Geriye dönük uyumluluk: eski ad.
VehicleState = EnvelopeState


@dataclass
class Command:
    bank_deg: float
    pitch_deg: float
    airspeed_mps: float


@dataclass
class Envelope:
    min_alt_m: float = 30.0
    min_airspeed_mps: float = 17.0   # seyirde; Vs ≈ 15,4 m/s -> ~1,1·Vs
    max_airspeed_mps: float = 38.0
    max_bank_deg: float = 50.0
    max_pitch_deg: float = 25.0
    min_fence_dist_m: float = 50.0

    def violations(self, s: VehicleState, scale: float = 1.0) -> list[str]:
        """scale > 1 zarfı daraltır (daha temkinli), < 1 genişletir."""
        out = []
        if s.alt_agl_m < self.min_alt_m * scale:
            out.append("alcak_irtifa")
        if s.airspeed_mps < self.min_airspeed_mps * scale:
            out.append("dusuk_hava_hizi")
        if s.airspeed_mps > self.max_airspeed_mps / scale:
            out.append("yuksek_hava_hizi")
        if abs(s.bank_deg) > self.max_bank_deg / scale:
            out.append("asiri_yatis")
        if abs(s.pitch_deg) > self.max_pitch_deg / scale:
            out.append("asiri_yunuslama")
        if s.fence_dist_m < self.min_fence_dist_m * scale:
            out.append("geofence")
        return out

    def margin(self, s: VehicleState) -> float:
        """Normalize en küçük zarf payı (<0 ihlal). Metrikler için."""
        return min((s.alt_agl_m - self.min_alt_m) / self.min_alt_m,
                   (s.airspeed_mps - self.min_airspeed_mps) / self.min_airspeed_mps,
                   (self.max_airspeed_mps - s.airspeed_mps) / self.max_airspeed_mps,
                   (self.max_bank_deg - abs(s.bank_deg)) / self.max_bank_deg,
                   (self.max_pitch_deg - abs(s.pitch_deg)) / self.max_pitch_deg,
                   (s.fence_dist_m - self.min_fence_dist_m) / self.min_fence_dist_m)


SafetyEnvelope = Envelope


def predict(s: VehicleState, c: Command, horizon_s: float,
            tau_att_s: float = 0.6, tau_speed_s: float = 4.0) -> VehicleState:
    """Birinci derece tepki + kinematik ile kaba ileri kestirim.

    Muhafazakârlık: tırmanma hızı yalnızca kötüleşme yönünde dikkate alınır
    ve sınıra yaklaşma hızı sabit varsayılır.
    """
    k_att = 1.0 - math.exp(-horizon_s / tau_att_s)
    k_spd = 1.0 - math.exp(-horizon_s / tau_speed_s)
    bank = s.bank_deg + (c.bank_deg - s.bank_deg) * k_att
    pitch = s.pitch_deg + (c.pitch_deg - s.pitch_deg) * k_att
    aspd = s.airspeed_mps + (c.airspeed_mps - s.airspeed_mps) * k_spd
    # komutlanan yunuslamanın yaklaşık tırmanma etkisi
    climb = s.climb_mps + aspd * math.sin(math.radians(pitch)) * k_att * 0.5
    alt = s.alt_agl_m + min(climb, s.climb_mps) * horizon_s
    fence = s.fence_dist_m - max(s.fence_closing_mps, 0.0) * horizon_s
    return VehicleState(alt, aspd, bank, pitch, climb, fence, s.fence_closing_mps)


class StatePredictor(Protocol):
    def predict(self, s: VehicleState, c: Command, horizon_s: float) -> VehicleState: ...


@dataclass(frozen=True)
class KinematicPredictor:
    """Varsayılan kestirici: `predict` fonksiyonunu sarar."""
    tau_att_s: float = 0.6
    tau_speed_s: float = 4.0

    def predict(self, s: VehicleState, c: Command, horizon_s: float) -> VehicleState:
        return predict(s, c, horizon_s, self.tau_att_s, self.tau_speed_s)


@dataclass(frozen=True)
class SafetyDecision:
    """RTA'nın her çevrimdeki açıklanabilir kararı (GCS / tekrar oynatma)."""
    selected_source: Source
    command: Command
    reasons: tuple[str, ...]
    current_violations: tuple[str, ...]      # sert zarf, şimdiki durum
    predicted_violations: tuple[str, ...]    # yumuşak zarf, ufuk sonunda (AC ile)
    latched: bool
    prediction_horizon_s: float
    timestamp: float
    switched: bool                           # bu çevrimde kaynak değişti mi

    def to_dict(self) -> dict[str, Any]:
        return {"selected_source": self.selected_source.value,
                "command": {"bank_deg": round(self.command.bank_deg, 4),
                            "pitch_deg": round(self.command.pitch_deg, 4),
                            "airspeed_mps": round(self.command.airspeed_mps, 4)},
                "reasons": list(self.reasons),
                "current_violations": list(self.current_violations),
                "predicted_violations": list(self.predicted_violations),
                "latched": self.latched,
                "prediction_horizon_s": self.prediction_horizon_s,
                "timestamp": round(self.timestamp, 6), "switched": self.switched}


@dataclass
class RuntimeAssurance:
    soft: Envelope = field(default_factory=Envelope)
    hard: Envelope = field(default_factory=lambda: Envelope(
        min_alt_m=15.0, min_airspeed_mps=15.0, max_airspeed_mps=42.0,
        max_bank_deg=65.0, max_pitch_deg=35.0, min_fence_dist_m=10.0))
    horizon_s: float = 3.0
    recovery_margin: float = 1.2
    recovery_cycles: int = 50          # 50 Hz'de 1 s
    predictor: StatePredictor = field(default_factory=KinematicPredictor)

    def __post_init__(self) -> None:
        self.source = Source.ADVANCED
        self.latched = False
        self._ok_count = 0
        self.last_reasons: list[str] = []
        self.last_decision: SafetyDecision | None = None

    def decide(self, s: VehicleState, ac: Command, sc: Command,
               timestamp: float = 0.0) -> SafetyDecision:
        prev = self.source
        hard = self.hard.violations(s)
        predicted = self.soft.violations(self.predictor.predict(s, ac, self.horizon_s))
        if hard:
            self.latched = True
        if self.latched:
            self.source, self.last_reasons = Source.SAFETY, ["kilitli"] + hard
        elif self.source is Source.ADVANCED:
            if predicted:
                self.source, self.last_reasons = Source.SAFETY, list(predicted)
                self._ok_count = 0
        else:
            ok_now = not self.soft.violations(s, scale=self.recovery_margin)
            self._ok_count = self._ok_count + 1 if (ok_now and not predicted) else 0
            if self._ok_count >= self.recovery_cycles:
                self.source, self.last_reasons = Source.ADVANCED, []

        cmd = ac if self.source is Source.ADVANCED else sc
        self.last_decision = SafetyDecision(
            self.source, cmd, tuple(self.last_reasons), tuple(hard), tuple(predicted),
            self.latched, self.horizon_s, timestamp, self.source is not prev)
        return self.last_decision

    def select(self, s: VehicleState, ac: Command, sc: Command) -> tuple[Command, Source]:
        d = self.decide(s, ac, sc)
        return d.command, d.selected_source

    def reset(self) -> None:
        """Yalnızca yerde, operatör onayıyla çağrılır."""
        self.__post_init__()
