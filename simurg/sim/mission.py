"""Görev yöneticisi: nominal mod ilerleyişi ve görev ilerlemesi.

Sorumluluk: hangi nominal mod geçişinin İSTENECEĞİNE karar vermek (kalkış ->
geçiş -> görev -> dönüş -> iniş) ve görev ilerlemesini (ara noktalar, iptal,
tamamlanma) tutmak. Geçişi mod makinesi uygular; acil durum kararları
`ContingencyManager`'a aittir. Bu sınıf olay yayınlamaz, fizik bilmez.

Görev sonucu gerekçesi (`outcome_reason`) tekrar oynatmada "neden görev
tamamlanmadı?" sorusunu yanıtlamak için tutulur.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..core.config import SafetyConfig
from ..modes.flight_modes import Mode
from .scenario import MissionProfile


@dataclass(frozen=True)
class MissionView:
    mode: Mode
    t: float
    pos_ne: np.ndarray
    altitude_m: float
    nav_ok: bool
    link_up: bool
    landed: bool


@dataclass(frozen=True)
class ModeRequest:
    target: Mode
    reason: str


class MissionManager:
    COMPLETE_RADIUS_M = 30.0

    def __init__(self, profile: MissionProfile, safety: SafetyConfig) -> None:
        self.p = profile
        self.safety = safety
        self.home = np.array(profile.home_ne, float)
        self.wp_index = 0
        self.waypoints_done = False
        self.aborted = False
        self.abort_reason = ""
        self.completed = False
        self.loiter_since = 0.0

    # ---- sorgular ---------------------------------------------------------
    def dist_home(self, pos_ne: np.ndarray) -> float:
        return float(np.linalg.norm(pos_ne - self.home))

    def guidance_target(self, mode: Mode) -> np.ndarray:
        if mode in (Mode.MISSION, Mode.CRUISE) and not self.aborted \
                and self.wp_index < len(self.p.waypoints):
            return np.array(self.p.waypoints[self.wp_index], float)
        return self.home

    def outcome_reason(self, final_mode: str, impact: bool, timed_out: bool) -> str:
        if self.completed:
            return "tamamlandi"
        if impact:
            return "carpma"
        if self.aborted:
            return f"iptal:{self.abort_reason}"
        if final_mode in ("DISARMED",):
            return "ara_noktalar_tamamlanmadan_indi"
        return "sure_doldu" if timed_out else "devam_ediyor"

    # ---- olay girişleri -----------------------------------------------------
    def abort(self, reason: str) -> bool:
        """Görevi iptal eder; ilk iptalse True."""
        if self.aborted:
            return False
        self.aborted, self.abort_reason = True, reason
        return True

    def on_mode_entered(self, mode: Mode, t: float) -> None:
        if mode is Mode.LOITER_HOLD:
            self.loiter_since = t

    # ---- adım ---------------------------------------------------------------
    def step(self, v: MissionView) -> tuple[ModeRequest | None, bool]:
        """(istenen nominal geçiş, bu adımda görev tamamlandı mı)."""
        m, p = v.mode, self.p
        if m is Mode.VTOL_TAKEOFF and v.altitude_m >= p.takeoff_alt_m - 1.0:
            return ModeRequest(Mode.TRANSITION_FW, "kalkis_irtifasi"), False
        if m is Mode.CRUISE:
            if self.waypoints_done or self.aborted:
                return ModeRequest(Mode.RETURN, "gorev_bitti"), False
            if v.nav_ok:
                return ModeRequest(Mode.MISSION, "gorev"), False
            return None, False
        if m is Mode.MISSION:
            wps = p.waypoints
            if self.wp_index < len(wps) and \
                    np.linalg.norm(v.pos_ne - wps[self.wp_index]) < p.waypoint_radius_m:
                self.wp_index += 1
            if self.wp_index >= len(wps):
                self.waypoints_done = True
                return ModeRequest(Mode.RETURN, "ara_noktalar_tamam"), False
            return None, False
        if m is Mode.RETURN and self.dist_home(v.pos_ne) < p.back_transition_dist_m:
            return ModeRequest(Mode.TRANSITION_VTOL, "yaklasma"), False
        if m is Mode.LOITER_HOLD:
            if v.nav_ok and v.link_up:
                return ModeRequest(Mode.CRUISE, "nav_geri_geldi"), False
            if v.t - self.loiter_since > self.safety.loiter_timeout_s:
                return ModeRequest(Mode.RETURN, "bekleme_zaman_asimi"), False
            return None, False
        if m in (Mode.VTOL_LAND, Mode.EMERGENCY_LAND, Mode.PARACHUTE) and v.landed:
            done_now = (m is Mode.VTOL_LAND and self.waypoints_done and not self.completed
                        and self.dist_home(v.pos_ne) < self.COMPLETE_RADIUS_M)
            if done_now:
                self.completed = True
            return ModeRequest(Mode.DISARMED, "yere_indi"), done_now
        return None, False
