"""Test modülleri arasında paylaşılan senaryo sonucu önbelleği (süreç başına bir koşu)."""

from functools import lru_cache

from simurg.sim import SimulationEngine, get_scenario


@lru_cache(maxsize=None)
def scenario_result(name: str, seed: int = 0):
    return SimulationEngine(get_scenario(name, seed)).run()
