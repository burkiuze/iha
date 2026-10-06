"""Bir koşuyu JSON'a kaydedip tekrar oynatma oturumuyla yeniden analiz eder."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from simurg.sim import ReplaySession, SimulationEngine, get_scenario  # noqa: E402


def main() -> None:
    eng = SimulationEngine(get_scenario("rta_intervention", seed=1))
    eng.run()
    path = os.path.join(tempfile.gettempdir(), "simurg_rta_kayit.json")
    eng.recorder.to_json(path)
    print(f"kayıt: {path}")

    s = ReplaySession.from_source(path)
    print("Özet:", s.summary()["event_counts"])
    print("Mod geçmişi:")
    for t, src, tgt, why in s.mode_history():
        print(f"  {t:7.2f}  {src:>15s} -> {tgt:15s} ({why})")
    print("RTA neden müdahale etti?")
    for r in s.rta_history():
        print(f"  {r['time_s']:7.2f}  {r['event']}: kaynak={r['selected_source']}, "
              f"öngörülen ihlal={r['predicted_violations']}")
    st = s.state_at(47.0)
    print(f"t≈47 s durumu: irtifa {st['alt']} m, tutum {st['att_deg']}, RTA kaynağı {st['rta']}")


if __name__ == "__main__":
    main()
