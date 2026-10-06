"""Tail-sitter geçiş koordinatörü (VTOL <-> sabit kanat).

Katmanlama:

    FlightModeMachine   (ne zaman: mod ve koruma koşulları)
          │  start_forward()/start_back()
    TransitionCoordinator  (nasıl: yunuslama programı, σ, iptal ölçütleri)
          │  TransitionSetpoint
    FlightController / Allocation / Dynamics

Koordinatör saf bir durum makinesidir: fizik ya da olay yolu bilmez; her
çağrıda bir `TransitionStatus` döndürür. Olayları motor (engine) yayınlar.

İleri geçiş: yunuslama komutu 90°'den `pitch_final_deg`'e `pitch_rate`
ile iner. Tamamlanma: V >= `complete_airspeed` ve yunuslama <= `complete_pitch`.
İptal ölçütleri (herhangi biri): irtifa kaybı, zaman aşımı, sürekli eyleyici
doyması, sürekli yunuslama takip hatası.

Geri geçiş: yunuslama komutu 90°'ye yükselir; V <= `back_complete_airspeed`
ve yunuslama >= 70° olduğunda tamamlanır.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..control.effectiveness import blend_sigma


class TransitionPhase(str, Enum):
    IDLE = "idle"
    FORWARD = "forward"
    BACK = "back"
    COMPLETED = "completed"
    ABORTED = "aborted"


@dataclass(frozen=True)
class TransitionConfig:
    pitch_rate_deg_s: float = 12.0
    pitch_final_deg: float = 8.0
    complete_airspeed_mps: float = 20.0
    complete_pitch_deg: float = 20.0      # RTA yumuşak zarfı (25°) ile arasında pay
    timeout_s: float = 20.0
    max_altitude_loss_m: float = 10.0
    saturation_limit: float = 0.5          # doymuş eyleyici oranı
    saturation_persist_s: float = 1.5
    pitch_error_limit_deg: float = 25.0
    pitch_error_persist_s: float = 1.0
    back_pitch_rate_deg_s: float = 20.0
    back_complete_airspeed_mps: float = 6.0


@dataclass(frozen=True)
class TransitionStatus:
    phase: TransitionPhase
    pitch_cmd_deg: float
    sigma: float
    elapsed_s: float
    progress: float               # 0..1 (yunuslama programı)
    altitude_loss_m: float
    abort_reason: str = ""
    just_finished: bool = False   # bu çağrıda COMPLETED/ABORTED'a geçti


class TransitionCoordinator:
    def __init__(self, cfg: TransitionConfig | None = None) -> None:
        self.cfg = cfg or TransitionConfig()
        self.phase = TransitionPhase.IDLE
        self._t0 = 0.0
        self._alt0 = 0.0
        self._pitch_cmd = 90.0
        self._sat_time = 0.0
        self._err_time = 0.0
        self._min_alt = 0.0
        self.abort_reason = ""

    # ---- başlatma -------------------------------------------------------
    def start_forward(self, t: float, altitude_m: float) -> None:
        self._start(TransitionPhase.FORWARD, t, altitude_m, 90.0)

    def start_back(self, t: float, altitude_m: float, pitch_deg: float) -> None:
        self._start(TransitionPhase.BACK, t, altitude_m, pitch_deg)

    def _start(self, phase, t, alt, pitch) -> None:
        self.phase = phase
        self._t0, self._alt0, self._min_alt = t, alt, alt
        self._pitch_cmd = pitch
        self._sat_time = self._err_time = 0.0
        self.abort_reason = ""

    @property
    def active(self) -> bool:
        return self.phase in (TransitionPhase.FORWARD, TransitionPhase.BACK)

    # ---- adım ------------------------------------------------------------
    def update(self, t: float, dt: float, airspeed_mps: float, pitch_deg: float,
               altitude_m: float, saturation_fraction: float) -> TransitionStatus:
        c = self.cfg
        prev = self.phase
        self._min_alt = min(self._min_alt, altitude_m)
        alt_loss = max(self._alt0 - self._min_alt, 0.0)
        elapsed = t - self._t0

        if self.phase is TransitionPhase.FORWARD:
            self._pitch_cmd = max(self._pitch_cmd - c.pitch_rate_deg_s * dt, c.pitch_final_deg)
            self._sat_time = self._sat_time + dt if saturation_fraction > c.saturation_limit else 0.0
            err = abs(pitch_deg - self._pitch_cmd)
            self._err_time = self._err_time + dt if err > c.pitch_error_limit_deg else 0.0
            reason = ""
            if alt_loss > c.max_altitude_loss_m:
                reason = "irtifa_kaybi"
            elif elapsed > c.timeout_s:
                reason = "zaman_asimi"
            elif self._sat_time > c.saturation_persist_s:
                reason = "eyleyici_doymasi"
            elif self._err_time > c.pitch_error_persist_s:
                reason = "yunuslama_takip_hatasi"
            if reason:
                self.phase, self.abort_reason = TransitionPhase.ABORTED, reason
            elif airspeed_mps >= c.complete_airspeed_mps and pitch_deg <= c.complete_pitch_deg:
                self.phase = TransitionPhase.COMPLETED
        elif self.phase is TransitionPhase.BACK:
            self._pitch_cmd = min(self._pitch_cmd + c.back_pitch_rate_deg_s * dt, 90.0)
            if airspeed_mps <= c.back_complete_airspeed_mps and pitch_deg >= 70.0:
                self.phase = TransitionPhase.COMPLETED

        span = 90.0 - c.pitch_final_deg
        progress = min(max((90.0 - self._pitch_cmd) / span, 0.0), 1.0)
        return TransitionStatus(self.phase, self._pitch_cmd, blend_sigma(airspeed_mps),
                                elapsed, progress, alt_loss, self.abort_reason,
                                just_finished=self.phase is not prev)

    def reset(self) -> None:
        self.phase = TransitionPhase.IDLE
