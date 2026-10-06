"""6-DOF dijital ikiz: nominal görevi baştan sona koşturur ve özet basar.

    python3 examples/simulation_demo.py [senaryo] [tohum]
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from simurg.sim import SimulationEngine, get_scenario  # noqa: E402


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "nominal"
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    result = SimulationEngine(get_scenario(name, seed)).run()
    m = result.metrics
    print(f"Senaryo: {name} (tohum {seed}) -> {'BAŞARILI' if result.passed else 'BAŞARISIZ'}")
    print(f"  süre {m.duration_s:.1f} s, son mod {m.final_mode}, görev tamam: {m.mission_completed}")
    print(f"  geçiş: {m.transitions_completed} tamam / {m.transitions_aborted} iptal, "
          f"azami irtifa kaybı {m.max_transition_altitude_loss_m:.1f} m")
    print(f"  enerji: {m.energy_consumed_wh:.1f} Wh tüketildi, "
          f"{m.remaining_usable_energy_wh:.0f} Wh kullanılabilir kaldı")
    print(f"  RTA müdahalesi: {m.rta_interventions}, acil durum kararı: {m.contingencies}")
    print("  Olaylar:")
    for e in result.events:
        if e["type"] not in ("mode_rejected",):
            print(f"    {e['time_s']:7.2f}  {e['type']:24s} {e['message']}")
    for f in result.expectation_failures:
        print(f"  ! {f}")


if __name__ == "__main__":
    main()
