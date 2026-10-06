"""Basit simülasyon komut satırı arayüzü.

    python -m simurg.sim list
    python -m simurg.sim run nominal --seed 3 --json kayit.json
    python -m simurg.sim montecarlo combined_degraded --runs 10 --seed 0 --wind 6
    python -m simurg.sim montecarlo combined_degraded --wind 6 --reproduce <TOHUM>
    python -m simurg.sim replay kayit.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import replace

from ..core.config import EnvironmentConfig
from ..core.errors import SimurgError
from .engine import SimulationEngine
from .montecarlo import MonteCarloRunner, uniform
from .replay import ReplaySession
from .scenarios import SCENARIOS, get_scenario


def _cmd_list(_: argparse.Namespace) -> int:
    for name, f in SCENARIOS.items():
        print(f"{name:30s} {f(0).description}")
    return 0


def _cmd_run(a: argparse.Namespace) -> int:
    sc = get_scenario(a.scenario, a.seed)
    if a.duration:
        sc = replace(sc, duration_s=a.duration)
    res = SimulationEngine(sc).run()
    m = res.metrics
    print(f"senaryo={sc.name} tohum={sc.seed} sonuç={'BAŞARILI' if res.passed else 'BAŞARISIZ'}")
    print(json.dumps(m.to_dict(), ensure_ascii=False, indent=2))
    for f in res.expectation_failures:
        print(f"  - {f}")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(res.log, fh, ensure_ascii=False, sort_keys=True)
        print(f"kayıt yazıldı: {a.json}")
    return 0 if res.passed else 1


def _cmd_mc(a: argparse.Namespace) -> int:
    base = SCENARIOS[a.scenario] if a.scenario in SCENARIOS else None
    if base is None:
        get_scenario(a.scenario)          # anlamlı hata fırlatır

    def factory(seed: int, p: dict[str, float]):
        sc = base(seed)
        env = EnvironmentConfig(wind_ned_mps=(p["wind_n"], p["wind_e"], 0.0),
                                turbulence_std_mps=p["turbulence"])
        return replace(sc, environment=env, vehicle=sc.vehicle.with_mass_scale(p["mass_scale"]))

    dists = {"wind_n": uniform(-a.wind, a.wind), "wind_e": uniform(-a.wind, a.wind),
             "turbulence": uniform(0.0, a.turbulence), "mass_scale": uniform(0.95, 1.05)}
    runner = MonteCarloRunner(factory, a.runs, a.seed, dists)
    if a.reproduce is not None:
        res = runner.reproduce(a.reproduce)
        print(json.dumps({"seed": a.reproduce, "params": runner.sample_params(a.reproduce),
                          "passed": res.passed, "failures": res.expectation_failures,
                          "metrics": res.metrics.to_dict()}, ensure_ascii=False, indent=2))
        return 0 if res.passed else 1
    rep = runner.run()
    print(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2))
    for s in rep.failed_seeds:
        print(f"yeniden üret: python -m simurg.sim montecarlo {a.scenario} "
              f"--wind {a.wind} --turbulence {a.turbulence} --reproduce {s}")
    return 0 if rep.failure_count == 0 else 1


def _cmd_replay(a: argparse.Namespace) -> int:
    s = ReplaySession.from_source(a.log)
    print(json.dumps(s.summary(), ensure_ascii=False, indent=2))
    for t, typ, msg in s.timeline():
        print(f"{t:9.2f}  {typ:24s} {msg}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m simurg.sim",
                                description="SİMURG araştırma simülasyonu (uçuş yazılımı değildir)")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="senaryoları listele").set_defaults(fn=_cmd_list)
    r = sub.add_parser("run", help="tek senaryo koş")
    r.add_argument("scenario")
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("--duration", type=float, default=None)
    r.add_argument("--json", default=None, help="kayıt JSON dosyası")
    r.set_defaults(fn=_cmd_run)
    mc = sub.add_parser("montecarlo", help="Monte Carlo kampanyası")
    mc.add_argument("scenario")
    mc.add_argument("--runs", type=int, default=10)
    mc.add_argument("--seed", type=int, default=0)
    mc.add_argument("--wind", type=float, default=5.0, help="yatay rüzgâr bileşeni sınırı (m/s)")
    mc.add_argument("--turbulence", type=float, default=1.0)
    mc.add_argument("--reproduce", type=int, default=None, metavar="SEED",
                    help="tek bir koşuyu tohumuyla yeniden üret")
    mc.set_defaults(fn=_cmd_mc)
    rp = sub.add_parser("replay", help="kaydı yeniden analiz et")
    rp.add_argument("log")
    rp.set_defaults(fn=_cmd_replay)
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    try:
        return a.fn(a)
    except SimurgError as e:
        print(f"hata: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
