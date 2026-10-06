"""Yer teması: temas algılama ve temasın güvenli/çarpma sınıflandırması."""

from __future__ import annotations

from dataclasses import dataclass

from ..modes.flight_modes import Mode

# Sınıflandırma eşikleri (m/s, derece). Sentetik güvenlik ölçütleri.
VERTICAL_MAX_DOWN = 3.0
VERTICAL_MAX_HORIZONTAL = 3.0
VERTICAL_MIN_PITCH_DEG = 60.0
GLIDE_MAX_DOWN = 3.5
PARACHUTE_MAX_DOWN = 7.0
_VERTICAL_MODES = {Mode.VTOL_LAND, Mode.VTOL_TAKEOFF, Mode.EMERGENCY_LAND, Mode.TRANSITION_VTOL}


@dataclass(frozen=True)
class Touchdown:
    safe: bool
    kind: str
    vertical_speed_mps: float
    horizontal_speed_mps: float
    pitch_deg: float
    mode: str

    def to_dict(self) -> dict:
        return {"kind": self.kind, "safe": self.safe,
                "vertical_speed_mps": round(self.vertical_speed_mps, 4),
                "horizontal_speed_mps": round(self.horizontal_speed_mps, 4),
                "pitch_deg": round(self.pitch_deg, 3), "mode": self.mode,
                "reason": self.kind if self.safe else f"{self.kind}_sinir_asimi"}


def classify_touchdown(mode: Mode, emergency_vertical: bool, v_down: float, v_h: float,
                       pitch_deg: float) -> Touchdown:
    if mode is Mode.PARACHUTE:
        ok, kind = v_down <= PARACHUTE_MAX_DOWN, "parachute"
    elif mode is Mode.EMERGENCY_LAND and not emergency_vertical:
        ok, kind = v_down <= GLIDE_MAX_DOWN, "emergency_glide"
    elif mode in _VERTICAL_MODES:
        ok = (v_down <= VERTICAL_MAX_DOWN and v_h <= VERTICAL_MAX_HORIZONTAL
              and pitch_deg >= VERTICAL_MIN_PITCH_DEG)
        kind = "vertical"
    else:
        ok, kind = False, "uncontrolled"
    return Touchdown(ok, kind, v_down, v_h, pitch_deg, mode.name)
