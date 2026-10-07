"""Mimari-kod denetimi (architecture-vs-code audit).

Hem testler (`tests/test_architecture.py`) hem de üretilen denetim bölümü
(docs/15 §8) bu fonksiyonları kullanır; belgedeki sonuç ile testin
doğruladığı sonuç aynı koddan gelir.

Denetimler:
  1. Kod referansı: IMPLEMENTED/PARTIAL/UNVALIDATED her blok var olan bir
     dosya + sembole işaret eder; PLANNED blok kod iddia etmez.
  2. Kapsam: güvenlik açısından kritik modüllerdeki her genel sınıf kayıtta
     bir bloğa bağlıdır (ya da gerekçeli olarak mimari dışıdır).
  3. RTA atlama: öneri katmanından eyleyici bölgesine yetki geçidi
     (RTA_SELECTOR, MD_FSM) dışından komut/gözetim yolu yoktur.
  4. Doğrudan YZ -> eyleyici kenarı yoktur.
  5. Tekil hata noktaları: komut yolundaki yedeksiz bloklar listelenir ve
     her biri için azaltım notu bulunur.
  6. Fail-safe kuralları (unknown != healthy) testlerle eşleşir.
  7. Her olay türü bir kayıt kanalına düşer (arıza olayları kayda girer).
"""

from __future__ import annotations

import ast
import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from .model import CODE_BACKED, Architecture, EdgeKind, Status

ROOT = Path(__file__).resolve().parents[2]

# Eyleyici yetkisi taşıyan bölge.
ACTUATION_GROUPS = ("CTRL", "ALLOC", "FCC", "ACT")
AUTHORITY_KINDS = (EdgeKind.COMMAND, EdgeKind.SUPERVISORY)

# Kapsam denetimi yapılan güvenlik/uçuş-kritik modüller.
CRITICAL_MODULES = (
    "simurg/safety/rta.py", "simurg/safety/command_validator.py",
    "simurg/fdir/monitor.py", "simurg/fdir/lanes.py", "simurg/fdir/reports.py",
    "simurg/fdir/vehicle_health.py", "simurg/modes/flight_modes.py",
    "simurg/nav/integrity.py", "simurg/nav/providers.py", "simurg/power/energy_manager.py",
    "simurg/power/reserve.py", "simurg/sensing/pipeline.py", "simurg/control/allocation.py",
    "simurg/control/guidance.py", "simurg/control/transition.py",
    "simurg/control/flight_controller.py", "simurg/sim/preflight.py", "simurg/sim/supervisor.py",
    "simurg/sim/triplex.py", "simurg/sim/airdata.py", "simurg/sim/health.py",
    "simurg/sim/recorder.py", "simurg/sim/replay.py", "simurg/sim/link.py",
)

# Kayıtta ayrı blok olmayan, gerekçeli genel sınıflar (veri taşıyıcı / yardımcı).
NOT_ARCHITECTURAL: dict[str, str] = {
    "Source": "RTA kaynak etiketi (ADVANCED/SAFETY) — RTA_SELECTOR çıktısının alanı",
    "Command": "Öneri içeriği veri tipi — CV_PROPOSAL zarfının içeriği",
    "StatePredictor": "Protocol — RTA_PREDICTOR arayüzü",
    "ValidationResult": "Doğrulayıcı sonuç veri tipi — CV_VALIDATOR çıktısı",
    "Health": "Eski motor sağlık enum'u — FDIR_MOTOR_MON iç durumu",
    "TripleLaneVoter": "Eski (v0.1) oylayıcı; geriye dönük uyumluluk — FCC_VOTER yerini aldı",
    "LaneOutput": "Şerit çıktısı veri tipi — FCC_*_OUT",
    "LaneChange": "Şerit durum değişimi veri tipi — FCC_ISOLATION olayı",
    "VoteResult": "Oylama sonucu veri tipi — FCC_VOTER çıktısı",
    "FdirDomain": "FDIR alan enum'u — FDIR_* blokları",
    "FaultClass": "Arıza sınıfı enum'u — FDIR_REPORT alanı",
    "Domain": "Sağlık alanı enum'u — VH_MANAGER",
    "DomainHealth": "Alan sağlığı veri tipi — VH_MANAGER",
    "VehicleHealthLevel": "Seviye enum'u — VH_LEVEL",
    "Mode": "Mod enum'u — MD_FSM",
    "Context": "Mod koruma bağlamı — MD_FSM / MD_INPUTS",
    "TransitionRecord": "Mod geçiş kaydı — MD_FSM çıktısı",
    "ContingencyRule": "Kural veri tipi — MD_RULES",
    "ContingencyDecision": "Karar veri tipi — MD_CONTINGENCY çıktısı",
    "PositionFix": "Konum ölçümü veri tipi — NAV_MEAS_VALID",
    "IntegrityResult": "Bütünlük sonucu veri tipi — NAV_INTEGRITY çıktısı",
    "NavigationProvider": "Protocol — NAV_SRC_MGR arayüzü",
    "PowerConfig": "Enerji parametreleri — CFG (mantıksal)",
    "PowerSplit": "Güç paylaşımı veri tipi — SEN_POWER_TLM",
    "EnergyDegradationModel": "Protocol — EN_SRC_HEALTH arayüzü",
    "ReserveAssessment": "Rezerv değerlendirmesi veri tipi — EN_RESERVE çıktısı",
    "Validity": "Ölçüm geçerlilik enum'u — SEN_SIGNAL_VALID",
    "Measurement": "Meta verili ölçüm veri tipi — SEN_MEAS_BUS",
    "HealthChange": "Kanal sağlık değişimi veri tipi — SEN_HEALTH olayı",
    "AllocationResult": "Dağıtım sonucu veri tipi — AL_RESIDUAL",
    "ScheduledAllocator": "Rejim zamanlamalı sarmalayıcı — AL_ALLOCATOR",
    "GuidanceGains": "Güdüm parametreleri (araştırma soyutlaması)",
    "TransitionPhase": "Geçiş fazı enum'u — G_TRANSITION",
    "TransitionConfig": "Geçiş parametreleri — G_TRANSITION",
    "TransitionStatus": "Geçiş durumu veri tipi — G_TRANSITION çıktısı",
    "AttitudeSetpoint": "Tutum hedefi veri tipi — C_ATT girdisi",
    "ControllerGains": "Kontrol parametreleri (araştırma soyutlaması; uçuş ayarı değil)",
    "FlightDemand": "Kontrol isteği veri tipi — AL_DEMAND",
    "PreflightCheck": "Kontrol sonucu veri tipi — PF_*",
    "PreflightReport": "Rapor veri tipi — PRE_SUPERVISOR çıktısı",
    "PreflightInputs": "Girdi veri tipi — PRE_SUPERVISOR",
    "SystemState": "Durum enum'u — SUP_SYSTEM",
    "SystemAssessment": "Değerlendirme veri tipi — SUP_SYSTEM çıktısı",
    "AirDataChange": "Hava verisi değişimi veri tipi — AIR_ADC olayı",
    "RejectClass": "Red sınıfı enum'u — CV_VALIDATOR",
    "ChannelSpec": "Kanal sınırları — SEN_PLAUSIBILITY",
}

# Fail-safe kuralı -> onu zorlayan testler ("modül.test").
FAILSAFE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Ölçümü olmayan sensör kanalı UNKNOWN; bayat ölçüm STALE",
     ("test_system_of_systems.test_channel_is_unknown_until_first_measurement",
      "test_system_of_systems.test_silent_source_goes_stale_on_bus")),
    ("Şerit ilk çıktıdan önce UNKNOWN; yalıtılmış şerit geri dönmez",
     ("test_system_of_systems.test_lanes_are_unknown_before_first_output",
      "test_system_of_systems.test_isolated_lane_cannot_rejoin_voter_as_nominal")),
    ("Araç sağlığında UNKNOWN asla NOMINAL değil",
     ("test_system_supervision.test_unknown_is_never_nominal",)),
    ("Gözlenmemiş motor havada askı hesabında çalışmıyor sayılır",
     ("test_failsafe.test_unobserved_motors_are_not_counted_for_hover_when_airborne",)),
    ("Çözümsüz navigasyon bütünlük bildirmez",
     ("test_failsafe.test_navigation_without_solution_never_reports_integrity",)),
    ("Sonlu olmayan durum RTA'da güvenli sayılmaz",
     ("test_safety_invariants.test_nonfinite_state_is_not_treated_as_safe",)),
    ("Bilinmeyen enerji / şerit / RTA / kayıt durumu uçuş öncesini geçmez",
     ("test_system_supervision.test_unknown_energy_does_not_pass",
      "test_system_supervision.test_unknown_lane_rta_and_recorder_state_do_not_pass")),
)


# Mimari güvenlik değişmezi -> onu zorlayan testler ("modül.test").
SAFETY_INVARIANTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("AI cannot bypass RTA", (
        "test_architecture.test_no_authority_path_bypasses_gates",
        "test_architecture.test_proposal_layer_has_no_direct_edges_to_actuation",
        "test_safety_invariants.test_ai_layer_has_no_import_path_to_actuation",
        "test_safety_invariants.test_controller_rejects_unvalidated_command",
        "test_safety_invariants.test_validated_command_cannot_be_forged")),
    ("RTA hard safety violation sırasında advanced command seçemez", (
        "test_safety_invariants.test_hard_envelope_violation_denies_advanced_authority",
        "test_safety_invariants.test_rta_latched_never_selects_advanced")),
    ("FAILED actuator nominal kabul edilemez / nominal dağıtıma alınmaz", (
        "test_safety_invariants.test_failed_actuator_not_treated_as_nominal",
        "test_system_of_systems.test_failed_actuator_receives_no_nominal_allocation")),
    ("Isolated FCC lane voter'a nominal lane olarak katılamaz", (
        "test_system_of_systems.test_isolated_lane_cannot_rejoin_voter_as_nominal",
        "test_system_of_systems.test_single_divergent_lane_never_reaches_output_and_is_isolated")),
    ("Unknown health != nominal", (
        "test_system_supervision.test_unknown_is_never_nominal",
        "test_system_of_systems.test_channel_is_unknown_until_first_measurement",
        "test_system_of_systems.test_lanes_are_unknown_before_first_output")),
    ("PARACHUTE gibi terminal acil durumdan normal göreve dönülemez", (
        "test_safety_invariants.test_parachute_mode_is_terminal_in_air",)),
    ("Kritik preflight hatası varken arming yapılamaz", (
        "test_system_supervision.test_each_failure_blocks_arming",
        "test_system_supervision.test_failed_preflight_never_arms_or_takes_off")),
    ("Invalid / stale komut uygulanamaz", (
        "test_system_of_systems.test_each_reject_class",
        "test_system_of_systems.test_stale_mission_computer_proposals_never_reach_rta",
        "test_system_supervision.test_invalid_ai_proposal_never_reaches_rta_in_simulation")),
    ("Mod yalnız state machine üzerinden değişir", (
        "test_safety_invariants.test_mode_changes_only_through_transition_table",)),
    ("Her güvenlik kararı kayıttan açıklanabilir", (
        "test_explainability.test_safety_events_carry_reason_and_component",
        "test_system_of_systems.test_every_event_type_belongs_to_a_recorder_channel",
        "test_system_of_systems.test_explainability_questions_answered_from_record")),
)


@dataclass(frozen=True)
class AuditResult:
    check: str
    passed: bool
    detail: str


# ---------------------------------------------------------------- yardımcılar
def members(a: Architecture, container: str) -> list[str]:
    return [c.id for c in a.components if c.group == container or c.sub == container]


def expand(a: Architecture, node: str) -> set[str]:
    return {node} if node in a.by_id() else set(members(a, node))


def successors(a: Architecture, kinds) -> dict[str, set[str]]:
    succ = {c.id: set() for c in a.components}
    for e in a.edges:
        if e.kind in kinds:
            for s in expand(a, e.src):
                succ[s] |= expand(a, e.dst)
    return succ


def reachable(a: Architecture, starts: set[str], kinds, stop_at=frozenset()) -> set[str]:
    succ = successors(a, kinds)
    seen, todo = set(starts), deque(starts)
    while todo:
        n = todo.popleft()
        if n in stop_at:
            continue
        for m in succ[n] - seen:
            seen.add(m)
            todo.append(m)
    return seen


def actuation_nodes(a: Architecture) -> set[str]:
    out: set[str] = set()
    for g in ACTUATION_GROUPS:
        out |= set(members(a, g))
    return out


def proposal_nodes(a: Architecture) -> set[str]:
    return {c.id for c in a.components if c.proposal_only}


def symbol_exists(ref: str) -> bool:
    path, _, symbol = ref.partition("::")
    f = ROOT / path
    if not f.is_file():
        return False
    if not symbol:
        return True
    name = re.escape(symbol.split(".")[-1])
    rx = re.compile(rf"^\s*(class|def)\s+{name}\b|^\s*{name}\s*(:[^=]*)?=", re.M)
    return bool(rx.search(f.read_text(encoding="utf-8")))


def public_classes(path: str) -> list[str]:
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    return [n.name for n in tree.body if isinstance(n, ast.ClassDef) and not n.name.startswith("_")]


# ---------------------------------------------------------------- denetimler
def bad_code_refs(a: Architecture) -> list[str]:
    out = []
    for c in a.components:
        if c.status in CODE_BACKED:
            if not c.code:
                out.append(f"{c.id}: {c.status.value} ama kod referansı yok")
            out += [f"{c.id}: {r}" for r in c.code if not symbol_exists(r)]
        elif c.code:
            out.append(f"{c.id}: PLANNED ama kod iddia ediyor")
    return out


def uncovered_critical_classes(a: Architecture) -> list[str]:
    referenced = {(r.partition("::")[0], r.partition("::")[2].split(".")[-1])
                  for c in a.components for r in c.code}
    out = []
    for path in CRITICAL_MODULES:
        for cls in public_classes(path):
            if (path, cls) not in referenced and cls not in NOT_ARCHITECTURAL:
                out.append(f"{path}::{cls}")
    return out


def authority_leaks(a: Architecture) -> set[str]:
    reached = reachable(a, proposal_nodes(a), AUTHORITY_KINDS, stop_at=a.gates)
    return (reached - a.gates) & actuation_nodes(a)


def direct_proposal_edges(a: Architecture) -> list[str]:
    act = actuation_nodes(a) | set(ACTUATION_GROUPS)
    act |= {sid for g in a.groups if g.id in ACTUATION_GROUPS for sid, _ in g.subgroups}
    return [f"{e.src}->{e.dst}" for e in a.edges
            if e.src in proposal_nodes(a) and e.dst in act]


def gate_reaches_actuators(a: Architecture) -> bool:
    return bool(reachable(a, {"RTA_SELECTOR"}, (EdgeKind.COMMAND,)) & set(members(a, "ACT_M")))


def command_path(a: Architecture) -> set[str]:
    """Öneri/güvenlik kaynaklarından eyleyicilere giden KOMUT yolundaki bloklar."""
    starts = proposal_nodes(a) | {"C_SAFETY"}
    fwd = reachable(a, starts, (EdgeKind.COMMAND,))
    targets = set(members(a, "ACT_M")) | set(members(a, "ACT_E"))
    rev: dict[str, set[str]] = {c.id: set() for c in a.components}
    for s, ds in successors(a, (EdgeKind.COMMAND,)).items():
        for d in ds:
            rev[d].add(s)
    back, todo = set(targets), deque(targets)
    while todo:
        n = todo.popleft()
        for m in rev[n] - back:
            back.add(m)
            todo.append(m)
    return fwd & back


def spof_candidates(a: Architecture) -> list[str]:
    by = a.by_id()
    return sorted(n for n in command_path(a) if not by[n].redundancy)


def unmitigated_spofs(a: Architecture) -> list[str]:
    mit = dict(a.spof_mitigation)
    return [n for n in spof_candidates(a) if n not in mit]


def missing_failsafe_tests(rules=None) -> list[str]:
    out = []
    for _, tests in (FAILSAFE_RULES if rules is None else rules):
        for t in tests:
            mod, name = t.split(".")
            f = ROOT / "tests" / f"{mod}.py"
            if not f.is_file() or f"def {name}(" not in f.read_text(encoding="utf-8"):
                out.append(t)
    return out


def unrecorded_event_types() -> list[str]:
    from ..core.events import EventType
    from ..sim.recorder import CHANNEL_OF
    return sorted(t.value for t in EventType if t.value not in CHANNEL_OF)


def failure_chain_problems(a: Architecture) -> list[str]:
    from ..core.events import EventType
    from ..sim.scenarios import SCENARIOS
    ids, types = set(a.by_id()), {t.value for t in EventType}
    out = []
    for ch in a.failure_chains:
        if ch.scenario not in SCENARIOS:
            out.append(f"{ch.id}: senaryo yok: {ch.scenario}")
        for stage in (ch.detection, ch.isolation, ch.degradation, ch.contingency):
            out += [f"{ch.id}: bilinmeyen blok {n}" for n in stage if n not in ids]
        out += [f"{ch.id}: bilinmeyen olay {ev}" for ev in ch.events if ev not in types]
    return out


def run(a: Architecture) -> list[AuditResult]:
    refs = bad_code_refs(a)
    unc = uncovered_critical_classes(a)
    leaks = sorted(authority_leaks(a))
    direct = direct_proposal_edges(a)
    spof = spof_candidates(a)
    unmit = unmitigated_spofs(a)
    fs = missing_failsafe_tests()
    unrec = unrecorded_event_types()
    fc = failure_chain_problems(a)
    inv = missing_failsafe_tests(SAFETY_INVARIANTS)
    n_code = sum(c.status in CODE_BACKED for c in a.components)
    return [
        AuditResult("Diyagramdaki her kod dayanaklı blok (IMPLEMENTED/PARTIAL/UNVALIDATED) kodda var mı?",
                    not refs, f"{n_code} blok, {sum(len(c.code) for c in a.components)} referans doğrulandı"
                    if not refs else "; ".join(refs)),
        AuditResult("Koddaki kritik sınıflar diyagramda var mı?", not unc,
                    f"{len(CRITICAL_MODULES)} modül tarandı; kapsanmayan yok "
                    f"({len(NOT_ARCHITECTURAL)} veri tipi gerekçeli olarak mimari dışı)"
                    if not unc else "; ".join(unc)),
        AuditResult("RTA'yı atlayan yetki yolu var mı?", not leaks,
                    "Yok: öneri katmanından eyleyici bölgesine her komut/gözetim yolu "
                    "RTA_SELECTOR ya da MD_FSM'den geçiyor" if not leaks else ", ".join(leaks)),
        AuditResult("Doğrudan YZ -> eyleyici kenarı var mı?", not direct,
                    "Yok" if not direct else ", ".join(direct)),
        AuditResult("Tekil hata noktası (SPOF) adayları belgelenmiş mi?", not unmit,
                    f"{len(spof)} yedeksiz komut yolu bloğu; tümünün azaltım notu var (§8.1)"
                    if not unmit else "Azaltımsız: " + ", ".join(unmit)),
        AuditResult("Bilinmeyen durum iyimser biçimde sağlıklı kabul ediliyor mu?", not fs,
                    f"Hayır: {len(FAILSAFE_RULES)} fail-safe kuralı testlerle zorlanıyor"
                    if not fs else "Eksik test: " + ", ".join(fs)),
        AuditResult("Arıza olayları kayda giriyor mu?", not unrec,
                    "Evet: her olay türü bir kayıt kanalına eşli" if not unrec
                    else "Kanalsız: " + ", ".join(unrec)),
        AuditResult("Güvenlik değişmezleri testlerle eşleşiyor mu?", not inv,
                    f"{len(SAFETY_INVARIANTS)} değişmez, hepsinin testi var (§8)"
                    if not inv else "Eksik test: " + ", ".join(inv)),
        AuditResult("Arıza zincirleri (§7) geçerli blok/olay/senaryoya mı bağlı?", not fc,
                    f"{len(a.failure_chains)} zincir; olaylar senaryo testinde doğrulanır"
                    if not fc else "; ".join(fc)),
    ]


def status_counts(a: Architecture) -> dict[Status, int]:
    return {s: sum(c.status is s for c in a.components) for s in Status}
