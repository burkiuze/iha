"""Komut doğrulayıcı (Command Validator / Sanitizer): YZ önerisi -> RTA arası.

Yetki zinciri:  YZ / görev planlayıcı --öneri--> CommandValidator --> Simplex RTA

Doğrulayıcı güvenlik kararı VERMEZ (bu RTA'nın işidir); yalnızca önerinin
RTA'nın değerlendirebileceği biçimde olup olmadığını denetler:

  * tip: `Command` olmalı
  * sonluluk: NaN/Inf içeremez (bilinmeyen != güvenli)
  * fiziksel akla yatkınlık: yatış/yunuslama/hız mutlak sınırlar içinde

Önerileri sessizce KIRPMAZ: kırpma, YZ'nin niyetini değiştirip RTA'ya
yanıltıcı girdi verirdi. Geçersiz öneri reddedilir ve gerekçesi döner;
o adımda kontrol yalnızca güvenlik kontrolcüsünden gelir.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .rta import Command


@dataclass(frozen=True)
class ProposalLimits:
    """Fiziksel akla yatkınlık sınırları (güvenlik zarfı DEĞİLDİR; o RTA'dadır)."""
    max_abs_bank_deg: float = 90.0
    max_abs_pitch_deg: float = 60.0
    min_airspeed_mps: float = 0.0
    max_airspeed_mps: float = 60.0


@dataclass(frozen=True)
class ValidationResult:
    accepted: bool
    command: Command | None
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return {"accepted": self.accepted, "reasons": list(self.reasons),
                "reason": ",".join(self.reasons) or "gecerli"}


class CommandValidator:
    def __init__(self, limits: ProposalLimits | None = None) -> None:
        self.limits = limits or ProposalLimits()

    def validate(self, proposal: object) -> ValidationResult:
        if not isinstance(proposal, Command):
            return ValidationResult(False, None, ("tip_gecersiz",))
        vals = (proposal.bank_deg, proposal.pitch_deg, proposal.airspeed_mps)
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in vals):
            return ValidationResult(False, None, ("sonlu_degil",))
        lim, reasons = self.limits, []
        if abs(proposal.bank_deg) > lim.max_abs_bank_deg:
            reasons.append("yatis_fiziksel_sinir_disi")
        if abs(proposal.pitch_deg) > lim.max_abs_pitch_deg:
            reasons.append("yunuslama_fiziksel_sinir_disi")
        if not lim.min_airspeed_mps <= proposal.airspeed_mps <= lim.max_airspeed_mps:
            reasons.append("hiz_fiziksel_sinir_disi")
        if reasons:
            return ValidationResult(False, None, tuple(reasons))
        return ValidationResult(True, proposal, ())
