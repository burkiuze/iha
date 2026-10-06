"""Uçtan uca senaryo: arama-kurtarma görevi sırasında üst üste gelen arızalar.

  t=0     VTOL kalkış, geçiş, seyir
  t=600   M2U pervanesi kuş çarpması sonucu hasar görür (%10 devir kaybı)
  t=900   GNSS sahteciliği başlar (~220 m kaydırma)
  t=1200  Otonom planlayıcı geofence'e doğru dik bir dönüş ister
  t=1500  M2U tamamen durur -> hover marjı yeniden hesaplanır
  t=1700  Komuta-kontrol bağlantısı kopar -> 30 s sonra otomatik eve dönüş

Çalıştırma:  python3 examples/senaryo_demo.py
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from simurg.config import WEIGHT_N, hover_effectiveness  # noqa: E402
from simurg.control.allocation import ControlAllocator  # noqa: E402
from simurg.fdir.monitor import MotorHealthMonitor  # noqa: E402
from simurg.modes.flight_modes import (Context, ContingencyManager,  # noqa: E402
                                       FlightModeMachine, Mode)
from simurg.nav.integrity import IntegrityMonitor, PositionFix  # noqa: E402
from simurg.power.energy_manager import EnergyManager  # noqa: E402
from simurg.safety.rta import Command, RuntimeAssurance, VehicleState  # noqa: E402
from simurg.swarm.auction import Agent, Task, allocate  # noqa: E402


def main():
    rng = np.random.default_rng(42)
    B, lo, hi = hover_effectiveness()
    alloc = ControlAllocator(B, lo, hi)
    fdir = MotorHealthMonitor()
    em = EnergyManager()
    nav = IntegrityMonitor()
    rta = RuntimeAssurance()
    fsm, cm = FlightModeMachine(), ContingencyManager()
    ctx = Context(preflight_ok=True)

    print("== Sürü görev dağıtımı ==")
    agents = [Agent(f"SIMURG-{i}", np.array([0.0, 50.0 * i]), e)
              for i, e in enumerate([1800, 1800, 600])]
    tasks = [Task(f"ARAMA-{j}", rng.uniform(-20000, 20000, 2), 300, 1 + j % 3)
             for j in range(9)]
    for aid, route in allocate(agents, tasks, np.zeros(2)).items():
        print(f"  {aid}: {route}")

    print("\n== Uçuş ==")
    fsm.request(Mode.ARMED, ctx)
    fsm.request(Mode.VTOL_TAKEOFF, ctx)
    ctx.landed, ctx.alt_agl_m = False, 45
    fsm.request(Mode.TRANSITION_FW, ctx)
    ctx.airspeed_mps = 24
    fsm.request(Mode.CRUISE, ctx)
    fsm.request(Mode.MISSION, ctx)
    print(f"  mod: {fsm.mode.name}  hover marjı: {alloc.hover_margin(WEIGHT_N):.2f}")

    truth = np.array([0.0, 0.0])
    events_done = set()
    for t in range(0, 1801):
        load = 3800.0 if t < 45 else (1500.0 if t < 60 else 590.0)
        em.step(1.0, load, solar_w=70.0)
        truth = truth + np.array([28.0, 0.0])

        rpm_cmd = np.full(8, 5200.0)
        rpm = rpm_cmd * (1 + rng.normal(0, 0.008, 8))
        if t >= 600:
            rpm[1] *= 0.90
        if t >= 1500:
            rpm[1] = 0.0
        h_motor = fdir.update(rpm_cmd, rpm)

        spoof = np.array([180.0, 130.0]) if t >= 900 else np.zeros(2)
        fixes = [PositionFix("GNSS", truth + rng.normal(0, 3, 2) + spoof, np.eye(2) * 9),
                 PositionFix("VIO", truth + rng.normal(0, 8, 2), np.eye(2) * 64),
                 PositionFix("TRN", truth + rng.normal(0, 15, 2), np.eye(2) * 225),
                 PositionFix("MAGNAV", truth + rng.normal(0, 25, 2), np.eye(2) * 625)]
        nr = nav.evaluate(fixes)
        ctx.nav_integrity_ok = nr.integrity_ok

        s = VehicleState(150, 28, 0, 2, 0, fence_dist_m=400 if t >= 1200 else 3000,
                         fence_closing_mps=28 if t >= 1200 else 0)
        ac = Command(60, 2, 28) if 1200 <= t < 1205 else Command(10, 2, 28)
        _, src = rta.select(s, ac, Command(0, 3, 26))

        health = np.concatenate([h_motor, np.ones(4)])
        ctx.hover_feasible = alloc.hover_margin(WEIGHT_N, health) > 1.05
        ctx.rth_energy_ok = em.return_home_feasible(
            float(np.linalg.norm(truth)), 26.0, 590.0)
        ctx.link_lost_s = max(t - 1700, 0)
        new_mode = cm.evaluate(fsm, ctx)

        def once(key, msg):
            if key not in events_done:
                events_done.add(key)
                print(f"  t={t:5d}s  {msg}")

        if fdir.state[1].name != "OK":
            once(fdir.state[1].name,
                 f"FDIR: M2U {fdir.state[1].name}, sağlık={h_motor[1]:.2f}, "
                 f"hover marjı={alloc.hover_margin(WEIGHT_N, health):.2f}")
        if nr.excluded:
            once("nav", f"NAV: dışlanan={nr.excluded}, PL={nr.protection_level_m:.1f} m, "
                        f"hata={np.linalg.norm(nr.position - truth):.1f} m")
        if src.value == "safety":
            once("rta", f"RTA: güvenlik kontrolcüsü devrede, neden={rta.last_reasons}")
        if new_mode:
            once(f"mode{new_mode}", f"ACİL DURUM: {new_mode.name}")

    print(f"\n  Son mod: {fsm.mode.name}")
    print(f"  Batarya SoC: {em.batt_soc:.2f}  H2 kalan: {em.h2_wh:.0f} Wh (kimyasal)")
    print(f"  Kullanılabilir enerji: {em.usable_energy_wh():.0f} Wh")


if __name__ == "__main__":
    main()
