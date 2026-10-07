"""Güdüm katmanı: gelişmiş kontrolcü önerileri ve güvenlik kontrolcüsü.

Simplex yapısında:
  * `MissionGuidance` "gelişmiş kontrolcü"dür (AC). Gerçek sistemde bunun
    yerinde öğrenen ya da optimizasyon tabanlı bir planlayıcı olabilir. Asla
    nihai yetkiye sahip değildir; çıktısı RTA'dan geçer.
  * `SafetyController` (SC) basit ve öngörülebilirdir: kanatları düzler,
    güvenli irtifayı tutar, geofence'e yaklaşılıyorsa üsse doğru döner.

Tüm komutlar `safety.rta.Command` tipindedir (bank, pitch, airspeed).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..core.frames import wrap_pi
from ..safety.rta import Command


def _course(vel_ned: np.ndarray, fallback: float) -> float:
    if float(np.hypot(vel_ned[0], vel_ned[1])) < 3.0:
        return fallback
    return math.atan2(vel_ned[1], vel_ned[0])


@dataclass(frozen=True)
class GuidanceGains:
    pitch_trim_deg: float = 5.0
    alt_gain_deg_per_m: float = 0.2
    climb_damp_deg_per_mps: float = 0.8
    max_pitch_deg: float = 15.0
    bank_gain: float = 1.0           # derece bank / derece rota hatası
    max_bank_deg: float = 35.0
    loiter_bank_deg: float = 25.0
    stall_guard_low_mps: float = 18.0   # bu hızın altında burun yukarı komut verilmez


class MissionGuidance:
    """Gelişmiş kontrolcü (AC): ara noktaya/hedefe rota + irtifa tutma."""

    def __init__(self, gains: GuidanceGains | None = None) -> None:
        self.g = gains or GuidanceGains()
        self.fault_bank_deg: float | None = None   # arıza enjeksiyonu kancası
        self.fault_stale = False                    # arıza: öneri donar (eski zaman damgası)
        self._frozen: tuple[Command, float] | None = None

    def stamp(self, cmd: Command, t: float) -> tuple[Command, float]:
        """Öneriye üretim zaman damgası verir. `fault_stale` iken ilk dondurulan
        öneri eski damgasıyla tekrar edilir (doğrulayıcı bayat olarak reddetmeli)."""
        if not self.fault_stale:
            self._frozen = None
            return cmd, t
        if self._frozen is None:
            self._frozen = (cmd, t)
        return self._frozen

    def pitch_for_altitude(self, alt: float, climb: float, alt_cmd: float,
                           limit: float | None = None, airspeed: float | None = None,
                           speed_cmd: float | None = None) -> float:
        g = self.g
        lim = g.max_pitch_deg if limit is None else limit
        th = g.pitch_trim_deg + g.alt_gain_deg_per_m * (alt_cmd - alt) \
            - g.climb_damp_deg_per_mps * climb
        upper = lim
        if airspeed is not None and speed_cmd is not None:
            # stall koruması: hız düştükçe izin verilen burun-yukarı açı azalır
            k = (airspeed - g.stall_guard_low_mps) / max(speed_cmd - 2.0 - g.stall_guard_low_mps, 1e-3)
            upper = g.pitch_trim_deg + (lim - g.pitch_trim_deg) * float(np.clip(k, 0.0, 1.0))
            if airspeed < g.stall_guard_low_mps:
                upper = 0.0
        return float(np.clip(th, -lim, upper))

    def to_point(self, pos_ned: np.ndarray, vel_ned: np.ndarray, heading: float,
                 target_ne: np.ndarray, alt_cmd: float, speed_cmd: float,
                 airspeed: float | None = None) -> Command:
        g = self.g
        desired = math.atan2(target_ne[1] - pos_ned[1], target_ne[0] - pos_ned[0])
        err = math.degrees(wrap_pi(desired - _course(vel_ned, heading)))
        bank = float(np.clip(g.bank_gain * err, -g.max_bank_deg, g.max_bank_deg))
        if self.fault_bank_deg is not None:
            bank = self.fault_bank_deg
        pitch = self.pitch_for_altitude(-pos_ned[2], -vel_ned[2], alt_cmd,
                                        airspeed=airspeed, speed_cmd=speed_cmd)
        return Command(bank, pitch, speed_cmd)

    def loiter(self, pos_ned: np.ndarray, vel_ned: np.ndarray, alt_cmd: float,
               speed_cmd: float, airspeed: float | None = None) -> Command:
        pitch = self.pitch_for_altitude(-pos_ned[2], -vel_ned[2], alt_cmd,
                                        airspeed=airspeed, speed_cmd=speed_cmd)
        bank = self.g.loiter_bank_deg if self.fault_bank_deg is None else self.fault_bank_deg
        return Command(bank, pitch, speed_cmd)


class SafetyController:
    """Güvenlik kontrolcüsü (SC): kanat düz, güvenli irtifa, geofence'ten uzaklaş."""

    def __init__(self, safe_alt_m: float = 100.0, airspeed_mps: float = 24.0,
                 turn_bank_deg: float = 30.0) -> None:
        self.safe_alt_m = safe_alt_m
        self.airspeed_mps = airspeed_mps
        self.turn_bank_deg = turn_bank_deg

    def command(self, pos_ned: np.ndarray, vel_ned: np.ndarray, heading: float,
                home_ne: np.ndarray, fence_dist_m: float, fence_closing_mps: float,
                fence_min_m: float, airspeed: float | None = None) -> Command:
        alt, climb = -pos_ned[2], -vel_ned[2]
        upper = 10.0 if airspeed is None or airspeed >= 20.0 else 0.0   # düşük hızda burun aşağı
        pitch = float(np.clip(3.0 + 0.1 * (self.safe_alt_m - alt) - 0.8 * climb, -5.0, upper))
        bank = 0.0
        if fence_closing_mps > 0 and fence_dist_m < 4 * fence_min_m + 3 * fence_closing_mps:
            desired = math.atan2(home_ne[1] - pos_ned[1], home_ne[0] - pos_ned[0])
            err = wrap_pi(desired - _course(vel_ned, heading))
            bank = math.copysign(self.turn_bank_deg, err)
        return Command(bank, pitch, self.airspeed_mps)
