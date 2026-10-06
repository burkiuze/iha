"""Kendi arıza takviminizi tanımlayıp tespit gecikmelerini ölçün.

Senaryo: nominal görev + askıda M1L verim kaybı + seyirde VIO dropout +
geçici C2 kesintisi. Yalnızca yazılım doğrulaması içindir.
"""

import os
import sys
from dataclasses import replace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from simurg.sim import Fault, FaultKind, FaultSchedule, SimulationEngine, get_scenario  # noqa: E402


def main() -> None:
    faults = FaultSchedule((
        Fault("motor", FaultKind.ACTUATOR_DEGRADED, "actuator:M1L", 6.0, severity=0.2,
              description="M1L itki kaybı"),
        Fault("vio", FaultKind.SENSOR_DROPOUT, "sensor:VIO", 50.0, 30.0,
              description="VIO geçici yok"),
        Fault("c2", FaultKind.LINK_LOSS, "link:c2", 70.0, 15.0, description="kısa C2 kesintisi"),
    ))
    sc = replace(get_scenario("nominal", seed=4), name="fault_injection_demo", faults=faults)
    r = SimulationEngine(sc).run()
    print(f"Sonuç: {r.metrics.final_mode}, görev tamam: {r.metrics.mission_completed}")
    print(f"Arıza: {r.metrics.fault_count}, tespit edilen: {r.metrics.faults_detected}")
    for fid, lat in r.metrics.detection_latency_s.items():
        print(f"  {fid:6s} tespit gecikmesi {lat:.2f} s")


if __name__ == "__main__":
    main()
