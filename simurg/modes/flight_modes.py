"""Uçuş modu durum makinesi ve otomatik acil durum (contingency) yöneticisi.

Geçişler açık bir tabloda tanımlıdır; tabloda olmayan geçiş reddedilir.
Her geçişin bir koruma (guard) fonksiyonu vardır. Acil durum geçişleri
(RETURN, LOITER_HOLD, EMERGENCY_LAND, PARACHUTE) operatör isteğinden
bağımsız olarak `ContingencyManager` tarafından tetiklenebilir.
"""

from __future__ import annotations

import math
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
    # Kayıt / açıklanabilirlik girdileri (kural tablosu bunları henüz tetikleyici
    # olarak kullanmaz; kararla birlikte kaydedilir):
    vehicle_health_level: str = "unknown"
    rta_latched: bool = False
    link_ok: bool = True


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


AIRBORNE_MODES = frozenset(_AIRBORNE)
FIXED_WING_MODES = frozenset({Mode.CRUISE, Mode.MISSION, Mode.RETURN, Mode.LOITER_HOLD})


@dataclass(frozen=True)
class TransitionRecord:
    """Bir mod geçiş isteğinin tam kaydı (kabul ya da ret)."""
    source: Mode
    target: Mode
    reason: str
    accepted: bool
    guard_result: bool | None     # None: tabloda böyle bir geçiş yok
    timestamp: float
    diagnostic: str

    def to_dict(self) -> dict:
        return {"source": self.source.name, "target": self.target.name,
                "reason": self.reason, "accepted": self.accepted,
                "guard_result": self.guard_result,
                "timestamp": None if math.isnan(self.timestamp) else round(self.timestamp, 6),
                "diagnostic": self.diagnostic}


class FlightModeMachine:
    """Geçiş tablosu (`TRANSITIONS`) tek doğruluk kaynağıdır.

    `request` geriye dönük uyumlu bool döndürür; `request_detailed` aynı
    işlemi yapıp `TransitionRecord` döndürür. `clock` (zaman kaynağı) ve
    `listener` (kayıt dinleyicisi) isteğe bağlıdır.
    """

    def __init__(self, clock: Callable[[], float] | None = None,
                 listener: Callable[[TransitionRecord], None] | None = None):
        self.mode = Mode.PREFLIGHT
        self.history: list[tuple[Mode, Mode, str]] = []
        self.records: list[TransitionRecord] = []
        self.clock = clock
        self.listener = listener

    def request(self, target: Mode, ctx: Context, reason: str = "operator") -> bool:
        return self.request_detailed(target, ctx, reason).accepted

    def request_detailed(self, target: Mode, ctx: Context,
                         reason: str = "operator") -> TransitionRecord:
        t = self.clock() if self.clock is not None else float("nan")
        src = self.mode
        guard = TRANSITIONS.get((src, target))
        if guard is None:
            rec = TransitionRecord(src, target, reason, False, None, t,
                                   f"tablo_disi_gecis:{src.name}->{target.name}")
        else:
            ok = bool(guard(ctx))
            rec = TransitionRecord(src, target, reason, ok, ok, t,
                                   "" if ok else "koruma_kosulu_saglanmadi")
            if ok:
                self.history.append((src, target, reason))
                self.mode = target
        self.records.append(rec)
        if self.listener is not None:
            self.listener(rec)
        return rec

    @staticmethod
    def allowed_targets(mode: Mode) -> list[Mode]:
        return [t for (s, t) in TRANSITIONS if s is mode]


@dataclass(frozen=True)
class ContingencyRule:
    priority: int                        # 1 = en yüksek
    trigger: str                         # tetikleyici kimliği (reason olarak da kullanılır)
    target: Mode | None                  # None: "bekle" (ör. nav yokken eve dönme)
    applies_in: frozenset[Mode]          # kuralın değerlendirildiği modlar
    condition: Callable[[Context], bool]
    description: str


_LINK_LOSS_RTH_S = 30.0
_ACTIVE = frozenset(AIRBORNE_MODES)
_ACTIVE_NO_EL = _ACTIVE - {Mode.EMERGENCY_LAND}

# Öncelik tablosu: TEK DOĞRULUK KAYNAĞI. docs/08-otonomi-ve-guvenlik.md §3
# tablosu bu listeyle `tests/test_mode_integration.py` içinde eşleştirilir.
CONTINGENCY_RULES: tuple[ContingencyRule, ...] = (
    ContingencyRule(1, "kontrol_kaybi", Mode.PARACHUTE, _ACTIVE,
                    lambda c: not c.controllable, "Araç kontrol edilemiyor"),
    ContingencyRule(2, "enerji_veya_hover_yok", Mode.EMERGENCY_LAND, _ACTIVE_NO_EL,
                    lambda c: not c.land_energy_ok or not c.hover_feasible,
                    "Hover mümkün değil veya iniş enerjisi yok"),
    ContingencyRule(3, "eve_donus_enerjisi_yok", Mode.EMERGENCY_LAND,
                    _ACTIVE_NO_EL - {Mode.TRANSITION_VTOL, Mode.VTOL_LAND},
                    lambda c: not c.rth_energy_ok, "Eve dönüş enerjisi yok"),
    ContingencyRule(4, "nav_butunluk_kaybi", Mode.LOITER_HOLD,
                    frozenset({Mode.CRUISE, Mode.MISSION, Mode.RETURN}),
                    lambda c: not c.nav_integrity_ok, "Navigasyon bütünlüğü kaybı"),
    ContingencyRule(5, "baglanti_kaybi_nav_yok", None, frozenset({Mode.LOITER_HOLD}),
                    lambda c: c.link_lost_s > _LINK_LOSS_RTH_S and not c.nav_integrity_ok,
                    "Bağlantı kaybı ama nav bütünlüğü yok: bekle"),
    ContingencyRule(6, "baglanti_kaybi", Mode.RETURN,
                    frozenset({Mode.CRUISE, Mode.MISSION, Mode.LOITER_HOLD}),
                    lambda c: c.link_lost_s > _LINK_LOSS_RTH_S, "C2 bağlantısı > 30 s yok"),
)


CONTINGENCY_INPUTS = ("vehicle_health_level", "nav_integrity_ok", "rth_energy_ok",
                      "land_energy_ok", "hover_feasible", "controllable", "link_ok",
                      "link_lost_s", "rta_latched")


@dataclass(frozen=True)
class ContingencyDecision:
    """Önerilen güvenli mod + gerekçe + öncelik + zaman damgası + girdi görüntüsü."""
    requested_mode: Mode | None
    reason: str
    priority: int
    trigger: str
    accepted: bool
    source_mode: Mode
    timestamp: float = float("nan")
    inputs: tuple[tuple[str, object], ...] = ()

    @property
    def recommended_safe_mode(self) -> Mode | None:
        return self.requested_mode

    def to_dict(self) -> dict:
        return {"requested_mode": None if self.requested_mode is None else self.requested_mode.name,
                "recommended_safe_mode": None if self.requested_mode is None
                else self.requested_mode.name,
                "reason": self.reason, "priority": self.priority, "trigger": self.trigger,
                "accepted": self.accepted, "source_mode": self.source_mode.name,
                "timestamp": None if math.isnan(self.timestamp) else round(self.timestamp, 6),
                "inputs": dict(self.inputs)}


class ContingencyManager:
    """Öncelik sırasına göre otomatik acil durum kararı (`CONTINGENCY_RULES`).

    Öncelik (yüksekten düşüğe):
      1. Kontrol edilemezlik            -> PARACHUTE
      2. İniş enerjisi yok / hover yok  -> EMERGENCY_LAND (sabit kanatla süzülerek)
      3. Eve dönüş enerjisi yok         -> EMERGENCY_LAND (en yakın güvenli alan)
      4. Navigasyon bütünlüğü kaybı     -> LOITER_HOLD (ataletsel + görsel tutma)
      5. Bağlantı kaybı + nav yok       -> bekle (LOITER_HOLD'da kal)
      6. Bağlantı kaybı > 30 s          -> RETURN

    İlk eşleşen kural karardır (geçiş reddedilse bile alt kurallara inilmez).
    """

    LINK_LOSS_RTH_S = _LINK_LOSS_RTH_S
    rules = CONTINGENCY_RULES

    def evaluate_detailed(self, fsm: FlightModeMachine, ctx: Context) -> ContingencyDecision | None:
        m = fsm.mode
        t = fsm.clock() if fsm.clock is not None else float("nan")
        inputs = tuple((k, getattr(ctx, k)) for k in CONTINGENCY_INPUTS)
        for r in self.rules:
            if m not in r.applies_in or not r.condition(ctx):
                continue
            if r.target is None:
                return ContingencyDecision(None, r.description, r.priority, r.trigger, False, m,
                                           t, inputs)
            # Mod değişimi YALNIZCA Flight Mode Machine üzerinden (koruma koşullarıyla).
            ok = fsm.request(r.target, ctx, r.trigger)
            return ContingencyDecision(r.target, r.description, r.priority, r.trigger, ok, m,
                                       t, inputs)
        return None

    def evaluate(self, fsm: FlightModeMachine, ctx: Context) -> Mode | None:
        d = self.evaluate_detailed(fsm, ctx)
        return d.requested_mode if d is not None and d.accepted else None
