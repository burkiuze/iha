"""Komut doğrulayıcı (Command Validator): öneri -> RTA arası aşamalı denetim.

Yetki zinciri:  YZ / görev bilgisayarı / güdüm --CommandProposal-->
                CommandValidator --> Simplex RTA --ValidatedCommand--> kontrol

Aşamalar (sabit sıra; ilk başarısız aşama sınıfı belirler):

  1. schema       zarf `CommandProposal`, içerik `Command`, alanlar sonlu  -> INVALID
  2. freshness    zaman damgası geleceği göstermez, yaşı <= max_age       -> STALE
  3. mode         öneri üretildiği mod == aktif mod ve mod öneri kabul eder -> INCOMPATIBLE
  4. bounds       fiziksel akla yatkınlık sınırları (zarf DEĞİL)          -> INVALID
  5. authority    kaynak kayıtlı öneri kaynağı, komut türü yetkili         -> UNKNOWN / UNAUTHORIZED

Doğrulayıcı güvenlik kararı VERMEZ (bu RTA'nın işidir) ve öneriyi sessizce
KIRPMAZ: kırpma YZ'nin niyetini değiştirip RTA'ya yanıltıcı girdi verirdi.
Reddedilen öneri RTA'ya ulaşmaz; o adımda yalnızca güvenlik kontrolcüsü
yetkilidir.

Geriye dönük uyumluluk: çıplak `Command` da kabul edilir; bu durumda
yalnızca şema ve sınır aşamaları uygulanır (zaman/mod/kaynak bilgisi yok).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from .rta import Command

STAGES = ("schema", "freshness", "mode_compatibility", "bounds", "authority")

# Öneri üretmesine izin verilen kaynaklar (yalnızca ÖNERİ; eyleyici yetkisi yok).
PROPOSAL_SOURCES = frozenset({"mission_guidance", "mission_ai", "advanced_controller"})
# Kabul edilen tek komut türü: tutum + hız hedefi. Eyleyici seviyesi komut yok.
ALLOWED_KINDS = frozenset({"attitude_speed"})
# Önerinin anlamlı olduğu modlar (sabit kanat rejimi; RTA zarfı tanımlı).
PROPOSAL_MODES = frozenset({"CRUISE", "MISSION", "RETURN", "LOITER_HOLD"})


class RejectClass(str, Enum):
    INVALID = "invalid"
    STALE = "stale"
    INCOMPATIBLE = "incompatible"
    UNKNOWN = "unknown"
    UNAUTHORIZED = "unauthorized"


@dataclass(frozen=True)
class ProposalLimits:
    """Fiziksel akla yatkınlık sınırları (güvenlik zarfı DEĞİLDİR; o RTA'dadır)."""
    max_abs_bank_deg: float = 90.0
    max_abs_pitch_deg: float = 60.0
    min_airspeed_mps: float = 0.0
    max_airspeed_mps: float = 60.0
    max_age_s: float = 0.1            # öneri tazelik sınırı


@dataclass(frozen=True)
class CommandProposal:
    """Öneri zarfı: içerik + kaynak + üretim zamanı + üretildiği mod."""
    command: object
    source: str
    timestamp: float
    mode: str
    kind: str = "attitude_speed"


@dataclass(frozen=True)
class ValidationResult:
    accepted: bool
    command: Command | None
    reasons: tuple[str, ...]
    category: RejectClass | None = None
    stage: str = ""
    source: str = ""
    age_s: float | None = None

    def to_dict(self) -> dict:
        return {"accepted": self.accepted, "reasons": list(self.reasons),
                "reason": ",".join(self.reasons) or "gecerli",
                "category": None if self.category is None else self.category.value,
                "stage": self.stage, "proposal_source": self.source,
                "age_s": None if self.age_s is None else round(self.age_s, 6)}


@dataclass
class CommandValidator:
    limits: ProposalLimits = field(default_factory=ProposalLimits)
    sources: frozenset[str] = PROPOSAL_SOURCES

    def validate(self, proposal: object, *, now: float | None = None,
                 mode: str | None = None) -> ValidationResult:
        if isinstance(proposal, CommandProposal):
            return self._staged(proposal, now, mode)
        return self._content(proposal, "")          # eski çağrı biçimi

    # ---- aşamalar -------------------------------------------------------------
    def _staged(self, p: CommandProposal, now: float | None, mode: str | None) -> ValidationResult:
        def reject(cat: RejectClass, stage: str, *why: str, age: float | None = None):
            return ValidationResult(False, None, tuple(why), cat, stage, p.source, age)

        # 1. schema
        if not isinstance(p.command, Command) or not isinstance(p.source, str) \
                or not isinstance(p.mode, str) or not _finite(p.timestamp):
            return reject(RejectClass.INVALID, "schema", "sema_gecersiz")
        if not _finite(p.command.bank_deg, p.command.pitch_deg, p.command.airspeed_mps):
            return reject(RejectClass.INVALID, "schema", "sonlu_degil")
        # 2. freshness
        age = None
        if now is None:
            return reject(RejectClass.STALE, "freshness", "dogrulayici_zamani_yok")
        age = now - p.timestamp
        if age < -1e-9:
            return reject(RejectClass.STALE, "freshness", "gelecek_zaman_damgasi", age=age)
        if age > self.limits.max_age_s:
            return reject(RejectClass.STALE, "freshness", "bayat_oneri", age=age)
        # 3. mode compatibility
        if mode is None or p.mode != mode:
            return reject(RejectClass.INCOMPATIBLE, "mode_compatibility", "mod_uyusmazligi", age=age)
        if mode not in PROPOSAL_MODES:
            return reject(RejectClass.INCOMPATIBLE, "mode_compatibility",
                          "mod_oneri_kabul_etmiyor", age=age)
        # 4. bounds
        r = self._bounds(p.command)
        if r:
            return reject(RejectClass.INVALID, "bounds", *r, age=age)
        # 5. authority
        if p.source not in self.sources:
            return reject(RejectClass.UNKNOWN, "authority", "bilinmeyen_kaynak", age=age)
        if p.kind not in ALLOWED_KINDS:
            return reject(RejectClass.UNAUTHORIZED, "authority", "yetkisiz_komut_turu", age=age)
        return ValidationResult(True, p.command, (), None, "", p.source, age)

    def _content(self, proposal: object, source: str) -> ValidationResult:
        if not isinstance(proposal, Command):
            return ValidationResult(False, None, ("tip_gecersiz",), RejectClass.INVALID, "schema", source)
        if not _finite(proposal.bank_deg, proposal.pitch_deg, proposal.airspeed_mps):
            return ValidationResult(False, None, ("sonlu_degil",), RejectClass.INVALID, "schema", source)
        r = self._bounds(proposal)
        if r:
            return ValidationResult(False, None, tuple(r), RejectClass.INVALID, "bounds", source)
        return ValidationResult(True, proposal, (), None, "", source)

    def _bounds(self, c: Command) -> list[str]:
        lim, reasons = self.limits, []
        if abs(c.bank_deg) > lim.max_abs_bank_deg:
            reasons.append("yatis_fiziksel_sinir_disi")
        if abs(c.pitch_deg) > lim.max_abs_pitch_deg:
            reasons.append("yunuslama_fiziksel_sinir_disi")
        if not lim.min_airspeed_mps <= c.airspeed_mps <= lim.max_airspeed_mps:
            reasons.append("hiz_fiziksel_sinir_disi")
        return reasons


def _finite(*vals: object) -> bool:
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
               for v in vals)
