"""Uçuş modu durum makinesi ve otomatik acil durum (contingency) yöneticisi.

Geçişler açık bir tabloda tanımlıdır; tabloda olmayan geçiş reddedilir.
Her geçişin bir koruma (guard) fonksiyonu vardır. Acil durum geçişleri
(RETURN, LOITER_HOLD, EMERGENCY_LAND, PARACHUTE) operatör isteğinden
bağımsız olarak `ContingencyManager` tarafından tetiklenebilir.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable


class Mode(Enum):
    PREFLIGHT = auto()
    ARMED = auto()
    VTOL_TAKEOFF = auto()
    TRANSITION_FW = auto()     # dikeyden yataya geçiş
    CRUISE = auto()
    MISSION = auto()
    RETURN = auto()
    LOITER_HOLD = auto()
    TRANSITION_VTOL = auto()   # yataydan dikeye geri geçiş
    VTOL_LAND = auto()
    EMERGENCY_LAND = auto()
    PARACHUTE = auto()
    DISARMED = auto()


@dataclass
class Context:
    preflight_ok: bool = False
    alt_agl_m: float = 0.0
    airspeed_mps: float = 0.0
    transition_speed_mps: float = 20.0
    link_lost_s: float = 0.0
    rth_energy_ok: bool = True
    land_energy_ok: bool = True
    nav_integrity_ok: bool = True
    hover_feasible: bool = True       # kontrol dağıtıcısının hover marjı > 1
    controllable: bool = True         # RTA + FDIR: araç kontrol edilebilir mi
    landed: bool = True


Guard = Callable[[Context], bool]

_T: dict[tuple[Mode, Mode], Guard] = {
    (Mode.PREFLIGHT, Mode.ARMED): lambda c: c.preflight_ok and c.landed,
    (Mode.ARMED, Mode.DISARMED): lambda c: c.landed,
    (Mode.ARMED, Mode.VTOL_TAKEOFF): lambda c: c.preflight_ok and c.hover_feasible,
    (Mode.VTOL_TAKEOFF, Mode.TRANSITION_FW): lambda c: c.alt_agl_m >= 40.0,
    (Mode.VTOL_TAKEOFF, Mode.VTOL_LAND): lambda c: True,
    (Mode.TRANSITION_FW, Mode.CRUISE): lambda c: c.airspeed_mps >= c.transition_speed_mps,
    (Mode.TRANSITION_FW, Mode.TRANSITION_VTOL): lambda c: True,   # iptal
    (Mode.CRUISE, Mode.MISSION): lambda c: c.nav_integrity_ok and c.rth_energy_ok,
    (Mode.MISSION, Mode.CRUISE): lambda c: True,
    (Mode.CRUISE, Mode.RETURN): lambda c: True,
    (Mode.MISSION, Mode.RETURN): lambda c: True,
    (Mode.CRUISE, Mode.LOITER_HOLD): lambda c: True,
    (Mode.MISSION, Mode.LOITER_HOLD): lambda c: True,
    (Mode.LOITER_HOLD, Mode.CRUISE): lambda c: c.nav_integrity_ok,
    (Mode.LOITER_HOLD, Mode.RETURN): lambda c: True,
    (Mode.RETURN, Mode.TRANSITION_VTOL): lambda c: True,
    (Mode.RETURN, Mode.LOITER_HOLD): lambda c: True,
    (Mode.CRUISE, Mode.TRANSITION_VTOL): lambda c: True,
    (Mode.TRANSITION_VTOL, Mode.VTOL_LAND): lambda c: c.airspeed_mps <= 6.0,
    (Mode.VTOL_LAND, Mode.DISARMED): lambda c: c.landed,
}

# Her havadaki moddan acil iniş ve paraşüte her zaman geçilebilir.
_AIRBORNE = {Mode.VTOL_TAKEOFF, Mode.TRANSITION_FW, Mode.CRUISE, Mode.MISSION,
             Mode.RETURN, Mode.LOITER_HOLD, Mode.TRANSITION_VTOL, Mode.VTOL_LAND,
             Mode.EMERGENCY_LAND}
for _m in _AIRBORNE:
    if _m is not Mode.EMERGENCY_LAND:
        _T[(_m, Mode.EMERGENCY_LAND)] = lambda c: True
    _T[(_m, Mode.PARACHUTE)] = lambda c: True
_T[(Mode.EMERGENCY_LAND, Mode.DISARMED)] = lambda c: c.landed
_T[(Mode.PARACHUTE, Mode.DISARMED)] = lambda c: c.landed

TRANSITIONS = _T


class FlightModeMachine:
    def __init__(self):
        self.mode = Mode.PREFLIGHT
        self.history: list[tuple[Mode, Mode, str]] = []

    def request(self, target: Mode, ctx: Context, reason: str = "operator") -> bool:
        guard = TRANSITIONS.get((self.mode, target))
        if guard is None or not guard(ctx):
            return False
        self.history.append((self.mode, target, reason))
        self.mode = target
        return True


class ContingencyManager:
    """Öncelik sırasına göre otomatik acil durum kararı.

    Öncelik (yüksekten düşüğe):
      1. Kontrol edilemezlik            -> PARACHUTE
      2. İniş enerjisi yok / hover yok  -> EMERGENCY_LAND (sabit kanatla süzülerek)
      3. Eve dönüş enerjisi yok         -> EMERGENCY_LAND (en yakın güvenli alan)
      4. Navigasyon bütünlüğü kaybı     -> LOITER_HOLD (ataletsel + görsel tutma)
      5. Bağlantı kaybı > 30 s          -> RETURN
    """

    LINK_LOSS_RTH_S = 30.0

    def evaluate(self, fsm: FlightModeMachine, ctx: Context) -> Mode | None:
        m = fsm.mode
        if m in (Mode.PARACHUTE, Mode.DISARMED, Mode.PREFLIGHT, Mode.ARMED):
            return None
        if not ctx.controllable:
            return self._go(fsm, Mode.PARACHUTE, ctx, "kontrol_kaybi")
        if m is Mode.EMERGENCY_LAND:
            return None
        if not ctx.land_energy_ok or not ctx.hover_feasible:
            return self._go(fsm, Mode.EMERGENCY_LAND, ctx, "enerji_veya_hover_yok")
        if not ctx.rth_energy_ok and m not in (Mode.TRANSITION_VTOL, Mode.VTOL_LAND):
            return self._go(fsm, Mode.EMERGENCY_LAND, ctx, "eve_donus_enerjisi_yok")
        if not ctx.nav_integrity_ok and m in (Mode.CRUISE, Mode.MISSION, Mode.RETURN):
            return self._go(fsm, Mode.LOITER_HOLD, ctx, "nav_butunluk_kaybi")
        if ctx.link_lost_s > self.LINK_LOSS_RTH_S and m in (
                Mode.CRUISE, Mode.MISSION, Mode.LOITER_HOLD):
            if m is Mode.LOITER_HOLD and not ctx.nav_integrity_ok:
                return None
            return self._go(fsm, Mode.RETURN, ctx, "baglanti_kaybi")
        return None

    @staticmethod
    def _go(fsm, target, ctx, reason):
        return target if fsm.request(target, ctx, reason) else None
