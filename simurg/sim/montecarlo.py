"""Monte Carlo yazılım simülasyonu altyapısı (docs/12 §1.2).

Her koşunun tohumu `SeedSequence(base_seed)`'ten türetilir ve kaydedilir.
Koşuya özgü parametreler YALNIZCA o koşunun tohumundan örneklenir; dolayısıyla
başarısız bir koşu yalnızca tohumuyla yeniden üretilebilir:

    report = MonteCarloRunner(factory, runs=20, base_seed=7).run()
    report.failed_seeds                # -> [..]
    runner.reproduce(seed)             # aynı sonucu verir

Tasarım paralelleştirmeye uygundur: `run_one(index, seed)` saf bir
fonksiyondur ve koşular arasında paylaşılan durum yoktur (ilk sürüm sıralı).
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from .engine import SimulationEngine, SimulationResult
from .scenario import Scenario

log = logging.getLogger(__name__)

Distribution = Callable[[np.random.Generator], float]
ScenarioFactory = Callable[[int, dict[str, float]], Scenario]


def uniform(lo: float, hi: float) -> Distribution:
    return lambda rng: float(rng.uniform(lo, hi))


def normal(mu: float, sigma: float) -> Distribution:
    return lambda rng: float(rng.normal(mu, sigma))


def choice(*values: float) -> Distribution:
    return lambda rng: float(values[int(rng.integers(len(values)))])


@dataclass(frozen=True)
class RunRecord:
    index: int
    seed: int
    params: dict[str, float]
    passed: bool
    failures: tuple[str, ...]
    metrics: dict[str, Any]


@dataclass
class MonteCarloReport:
    base_seed: int
    runs: list[RunRecord] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return sum(r.passed for r in self.runs)

    @property
    def failure_count(self) -> int:
        return len(self.runs) - self.success_count

    @property
    def failed_seeds(self) -> list[int]:
        return [r.seed for r in self.runs if not r.passed]

    @property
    def safety_intervention_count(self) -> int:
        return sum(int(r.metrics.get("rta_interventions", 0)) +
                   int(r.metrics.get("contingencies", 0)) for r in self.runs)

    def metric_distribution(self, key: str) -> dict[str, float]:
        vals = [float(r.metrics[key]) for r in self.runs
                if isinstance(r.metrics.get(key), (int, float))]
        if not vals:
            return {}
        s = sorted(vals)
        return {"n": len(s), "min": s[0], "max": s[-1], "mean": statistics.fmean(s),
                "p95": s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))]}

    def to_dict(self) -> dict[str, Any]:
        keys = ("duration_s", "energy_consumed_wh", "rta_interventions",
                "actuator_saturation_pct", "max_attitude_error_deg",
                "max_transition_altitude_loss_m")
        return {"base_seed": self.base_seed, "runs": len(self.runs),
                "success_count": self.success_count, "failure_count": self.failure_count,
                "failed_seeds": self.failed_seeds,
                "safety_intervention_count": self.safety_intervention_count,
                "metric_distribution": {k: self.metric_distribution(k) for k in keys},
                "records": [{"index": r.index, "seed": r.seed, "params": r.params,
                             "passed": r.passed, "failures": list(r.failures)} for r in self.runs]}


class MonteCarloRunner:
    def __init__(self, scenario_factory: ScenarioFactory, runs: int, base_seed: int = 0,
                 distributions: dict[str, Distribution] | None = None) -> None:
        if runs <= 0:
            raise ValueError("koşu sayısı pozitif olmalı")
        self.factory = scenario_factory
        self.runs = runs
        self.base_seed = int(base_seed)
        self.distributions = dict(distributions or {})

    def seeds(self) -> list[int]:
        children = np.random.SeedSequence(self.base_seed).spawn(self.runs)
        return [int(c.generate_state(1)[0]) for c in children]

    def sample_params(self, seed: int) -> dict[str, float]:
        rng = np.random.default_rng(np.random.SeedSequence([seed, 0x5EED]))
        return {k: d(rng) for k, d in sorted(self.distributions.items())}

    def run_one(self, index: int, seed: int) -> tuple[RunRecord, SimulationResult]:
        params = self.sample_params(seed)
        result = SimulationEngine(self.factory(seed, params)).run()
        rec = RunRecord(index, seed, params, result.passed, tuple(result.expectation_failures),
                        result.metrics.to_dict())
        if not result.passed:
            log.warning("Monte Carlo koşu %d başarısız (tohum=%d): %s", index, seed,
                        "; ".join(result.expectation_failures))
        return rec, result

    def run(self) -> MonteCarloReport:
        report = MonteCarloReport(self.base_seed)
        for i, seed in enumerate(self.seeds()):
            report.runs.append(self.run_one(i, seed)[0])
        return report

    def reproduce(self, seed: int) -> SimulationResult:
        return self.run_one(-1, seed)[1]
