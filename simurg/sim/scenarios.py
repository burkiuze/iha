"""Hazır araştırma senaryoları (yalnızca sivil uçuş güvenliği / doğrulama).

Her fonksiyon tohum alır ve değişmez bir `Scenario` döndürür. Senaryolar,
arıza tespiti, acil durum davranışı ve güvenli geri dönüş mantığını test
etmek için tasarlanmıştır.

Kısa görev profili kullanılır (simülasyon süresini makul tutmak için).
"""

from __future__ import annotations

from typing import Callable

from ..core.config import EnvironmentConfig
from ..core.errors import InvalidScenarioError
from ..core.events import EventType as E
from .faults import Fault, FaultKind, FaultSchedule
from .scenario import Expectations, InitialConditions, MissionProfile, Scenario

SHORT_MISSION = MissionProfile(waypoints=((700.0, 0.0), (700.0, 500.0)))
LANDED = ("DISARMED",)


def nominal(seed: int = 0) -> Scenario:
    return Scenario(
        "nominal", "Nominal arama-tarama görevi: kalkış, geçiş, iki ara nokta, dönüş, iniş.",
        duration_s=260.0, seed=seed, mission=SHORT_MISSION,
        expectations=Expectations(
            required_events=(E.TRANSITION_COMPLETED, E.MISSION_COMPLETE, E.TOUCHDOWN),
            final_modes=LANDED, mission_completed=True, max_rta_interventions=0),
        tags=("nominal",))


def nav_source_loss(seed: int = 0) -> Scenario:
    """GNSS ölçümü kalıcı olarak kesilir; kalan kaynaklarla bütünlük korunur."""
    return Scenario(
        "nav_source_loss", "GNSS kaynağı t=40 s'de kullanılamaz hâle gelir.",
        duration_s=260.0, seed=seed, mission=SHORT_MISSION,
        faults=FaultSchedule((Fault("F1", FaultKind.SENSOR_DROPOUT, "sensor:GNSS", 40.0,
                                    description="GNSS ölçümü yok"),)),
        expectations=Expectations(
            required_events=(E.NAV_SOURCE_UNAVAILABLE, E.MISSION_COMPLETE),
            forbidden_events=(E.IMPACT, E.NAV_INTEGRITY_LOST),
            final_modes=LANDED, mission_completed=True),
        tags=("navigation",))


def nav_integrity_loss(seed: int = 0) -> Scenario:
    """İki birincil kaynak geçici kaybolur -> bütünlük kaybı -> bekleme -> devam."""
    return Scenario(
        "nav_integrity_loss", "GNSS ve VIO t=45-85 s arasında yok; araç bekler, sonra devam eder.",
        duration_s=320.0, seed=seed, mission=SHORT_MISSION,
        faults=FaultSchedule((
            Fault("F1", FaultKind.SENSOR_DROPOUT, "sensor:GNSS", 45.0, 40.0, description="GNSS yok"),
            Fault("F2", FaultKind.SENSOR_DROPOUT, "sensor:VIO", 45.0, 40.0, description="VIO yok"),
        )),
        expectations=Expectations(
            required_events=(E.NAV_INTEGRITY_LOST, E.CONTINGENCY, E.NAV_INTEGRITY_RESTORED),
            visited_modes=("LOITER_HOLD",), final_modes=LANDED, mission_completed=True),
        tags=("navigation", "contingency"))


def single_actuator_degradation(seed: int = 0) -> Scenario:
    return Scenario(
        "single_actuator_degradation", "M2U pervanesi askıda %30 itki kaybeder.",
        duration_s=260.0, seed=seed, mission=SHORT_MISSION,
        faults=FaultSchedule((Fault("F1", FaultKind.ACTUATOR_DEGRADED, "actuator:M2U", 8.0,
                                    severity=0.3, description="pervane hasarı (sentetik)"),)),
        expectations=Expectations(required_events=(E.FDIR_WARNING,), final_modes=LANDED,
                                  mission_completed=True),
        tags=("fdir",))


def communication_loss(seed: int = 0) -> Scenario:
    return Scenario(
        "communication_loss", "C2 bağlantısı t=35 s'de kalıcı kopar; 30 s sonra eve dönüş.",
        duration_s=260.0, seed=seed, mission=SHORT_MISSION,
        faults=FaultSchedule((Fault("F1", FaultKind.LINK_LOSS, "link:c2", 35.0,
                                    description="C2 kaybı"),)),
        expectations=Expectations(
            required_events=(E.LINK_LOST, E.CONTINGENCY), visited_modes=("RETURN",),
            final_modes=LANDED, mission_completed=False),
        tags=("contingency",))


def energy_reserve_warning(seed: int = 0) -> Scenario:
    return Scenario(
        "energy_reserve_warning",
        "Yakıt hücresi kullanılamaz; t=60 s'de batarya kapasitesi yarıya iner -> uyarı, dönüş.",
        duration_s=260.0, seed=seed, mission=SHORT_MISSION,
        initial=InitialConditions(battery_soc=0.80, hydrogen_fraction=0.0),
        faults=FaultSchedule((Fault("F1", FaultKind.ENERGY_BATTERY_FADE, "energy:battery", 60.0,
                                    severity=0.5, description="kapasite kaybı (sentetik)"),)),
        expectations=Expectations(
            required_events=(E.ENERGY_WARNING, E.MISSION_ABORT), visited_modes=("RETURN",),
            final_modes=LANDED, mission_completed=False),
        tags=("energy",))


def rta_intervention(seed: int = 0) -> Scenario:
    return Scenario(
        "rta_intervention", "Gelişmiş kontrolcü t=45 s'de 4 s boyunca zarf dışı yatış önerir.",
        duration_s=260.0, seed=seed, mission=SHORT_MISSION,
        faults=FaultSchedule((Fault("F1", FaultKind.CONTROLLER_FAULT, "controller:advanced", 45.0,
                                    4.0, description="hatalı yatış önerisi"),)),
        expectations=Expectations(
            required_events=(E.RTA_INTERVENTION, E.RTA_RECOVERY, E.MISSION_COMPLETE),
            forbidden_events=(E.IMPACT, E.RTA_LATCHED), final_modes=LANDED,
            mission_completed=True),
        tags=("rta",))


def transition_abort(seed: int = 0) -> Scenario:
    return Scenario(
        "transition_abort",
        "Geçiş sırasında DC bara akım sınırı (batarya + süperkap) devreye girer; "
        "geçiş iptal edilir, araç askıya döner ve iner.",
        duration_s=200.0, seed=seed, mission=SHORT_MISSION,
        faults=FaultSchedule((Fault("F1", FaultKind.ENERGY_POWER_LIMIT, "energy:battery", 22.0,
                                    3.0, severity=0.75, description="bara güç sınırı"),)),
        expectations=Expectations(
            required_events=(E.TRANSITION_ABORTED, E.MISSION_ABORT),
            visited_modes=("TRANSITION_VTOL",), final_modes=LANDED, mission_completed=False),
        tags=("transition",))


def combined_degraded(seed: int = 0) -> Scenario:
    return Scenario(
        "combined_degraded",
        "Rüzgâr + türbülans, M3L verim kaybı, GNSS sapması (dışlanır), 20 s C2 kesintisi.",
        duration_s=300.0, seed=seed, mission=SHORT_MISSION,
        environment=EnvironmentConfig(wind_ned_mps=(3.0, 2.0, 0.0), turbulence_std_mps=0.8),
        faults=FaultSchedule((
            Fault("F1", FaultKind.ACTUATOR_DEGRADED, "actuator:M3L", 8.0, severity=0.25,
                  description="pervane hasarı"),
            Fault("F2", FaultKind.SENSOR_BIAS, "sensor:GNSS", 60.0,
                  params={"bias": [180.0, -120.0]}, description="GNSS konum sapması"),
            Fault("F3", FaultKind.LINK_LOSS, "link:c2", 80.0, 20.0, description="kısa C2 kesintisi"),
        )),
        expectations=Expectations(
            required_events=(E.FDIR_WARNING, E.NAV_SOURCE_REJECTED, E.LINK_LOST, E.LINK_RESTORED),
            final_modes=LANDED),
        tags=("combined",))


def hover_capability_loss(seed: int = 0) -> Scenario:
    """Aynı kanat ucundaki iki motor seyirde devre dışı -> hover imkânsız.

    Beklenen: acil durum kuralı 2 (`enerji_veya_hover_yok`), dikey iniş
    denenmez; araç sabit kanatla alçalarak yere temas eder.
    """
    return Scenario(
        "hover_capability_loss", "M1U + M1L seyirde devre dışı: hover yok, süzülerek acil iniş.",
        duration_s=200.0, seed=seed, mission=SHORT_MISSION,
        faults=FaultSchedule((
            Fault("F1", FaultKind.ACTUATOR_OFFLINE, "actuator:M1U", 50.0, description="motor kaybı"),
            Fault("F2", FaultKind.ACTUATOR_OFFLINE, "actuator:M1L", 50.0, description="motor kaybı"),
        )),
        expectations=Expectations(
            required_events=(E.FDIR_FAILURE, E.CONTINGENCY, E.TOUCHDOWN),
            visited_modes=("EMERGENCY_LAND",), final_modes=LANDED, mission_completed=False),
        tags=("contingency", "fdir"))


def loss_of_control(seed: int = 0) -> Scenario:
    """Dört dış motor ve tüm elevonlar kaybedilir -> kontrol kaybı -> paraşüt."""
    names = ("M1U", "M4U", "M1L", "M4L", "E1U", "E2U", "E1L", "E2L")
    return Scenario(
        "loss_of_control", "Çoklu eyleyici kaybı: acil iniş denenir, kontrol kaybında paraşüt.",
        duration_s=150.0, seed=seed, mission=SHORT_MISSION,
        faults=FaultSchedule(tuple(
            Fault(f"F{i + 1}", FaultKind.ACTUATOR_OFFLINE, f"actuator:{n}", 30.0)
            for i, n in enumerate(names))),
        expectations=Expectations(
            required_events=(E.CONTINGENCY, E.TOUCHDOWN), visited_modes=("PARACHUTE",),
            final_modes=LANDED, mission_completed=False),
        tags=("contingency",))


def fcc_lane_divergence(seed: int = 0) -> Scenario:
    """FCC şerit B çıktısı t=50 s'de sapar -> çapraz karşılaştırma -> yalıtım; görev sürer."""
    return Scenario(
        "fcc_lane_divergence", "Şerit B çıktısı kalıcı olarak sapar; oylayıcı B'yi yalıtır.",
        duration_s=260.0, seed=seed, mission=SHORT_MISSION,
        faults=FaultSchedule((Fault("F1", FaultKind.FCC_LANE_DIVERGENCE, "fcc:B", 50.0,
                                    params={"offset": 0.3}, description="şerit B sapması"),)),
        expectations=Expectations(
            required_events=(E.FCC_LANE_STATE_CHANGED, E.VEHICLE_HEALTH_CHANGED,
                             E.MISSION_COMPLETE),
            final_modes=LANDED, mission_completed=True, max_rta_interventions=0),
        tags=("fcc", "redundancy"))


def fcc_lane_loss(seed: int = 0) -> Scenario:
    """FCC şerit A kalp atışı t=40 s'de kesilir -> bekçi köpeği -> FAILED; ikili mod."""
    return Scenario(
        "fcc_lane_loss", "Şerit A kullanılamaz hâle gelir; B + C ile ikili modda devam.",
        duration_s=260.0, seed=seed, mission=SHORT_MISSION,
        faults=FaultSchedule((Fault("F1", FaultKind.FCC_LANE_UNAVAILABLE, "fcc:A", 40.0,
                                    description="şerit A kalp atışı yok"),)),
        expectations=Expectations(
            required_events=(E.FCC_LANE_STATE_CHANGED, E.MISSION_COMPLETE),
            final_modes=LANDED, mission_completed=True, max_rta_interventions=0),
        tags=("fcc", "redundancy"))


def mission_computer_failure(seed: int = 0) -> Scenario:
    """Görev bilgisayarı önerisi t=45 s'de 6 s donar (bayat zaman damgası).

    Beklenen: doğrulayıcı bayat öneriyi RTA'ya ulaştırmaz, o sürede güvenlik
    kontrolcüsü yetkilidir; öneri akışı düzelince görev tamamlanır.
    """
    return Scenario(
        "mission_computer_failure", "Görev bilgisayarı önerisi 6 s donar; bayat öneriler reddedilir.",
        duration_s=260.0, seed=seed, mission=SHORT_MISSION,
        faults=FaultSchedule((Fault("F1", FaultKind.CONTROLLER_FAULT, "controller:advanced", 45.0,
                                    6.0, params={"mode": "stale"},
                                    description="görev bilgisayarı takıldı"),)),
        expectations=Expectations(
            required_events=(E.COMMAND_REJECTED, E.COMMAND_ACCEPTED, E.MISSION_COMPLETE),
            forbidden_events=(E.IMPACT, E.RTA_LATCHED), final_modes=LANDED,
            mission_completed=True),
        tags=("mission_computer", "command_validation"))


SCENARIOS: dict[str, Callable[[int], Scenario]] = {
    f.__name__: f for f in (nominal, nav_source_loss, nav_integrity_loss,
                            single_actuator_degradation, communication_loss,
                            energy_reserve_warning, rta_intervention, transition_abort,
                            combined_degraded, hover_capability_loss, loss_of_control,
                            fcc_lane_divergence, fcc_lane_loss, mission_computer_failure)
}


def get_scenario(name: str, seed: int = 0) -> Scenario:
    try:
        return SCENARIOS[name](seed)
    except KeyError:
        raise InvalidScenarioError(
            f"bilinmeyen senaryo '{name}'; mevcut: {', '.join(SCENARIOS)}") from None
