"""SİMURG simülasyon çekirdeği / dijital ikiz (araştırma amaçlı, uçuş yazılımı değildir).

Temel giriş noktaları:
    from simurg.sim import SimulationEngine, get_scenario
    result = SimulationEngine(get_scenario("nominal", seed=1)).run()
"""

from .engine import TICK_ORDER, SimulationEngine, SimulationResult, run_scenario
from .faults import Fault, FaultInjector, FaultKind, FaultSchedule
from .metrics import SimulationMetrics
from .montecarlo import MonteCarloReport, MonteCarloRunner
from .recorder import SimulationRecorder, load_log
from .replay import ReplaySession
from .scenario import Expectations, InitialConditions, MissionProfile, Scenario
from .scenarios import SCENARIOS, get_scenario

__all__ = ["Expectations", "Fault", "FaultInjector", "FaultKind", "FaultSchedule",
           "InitialConditions", "MissionProfile", "MonteCarloReport", "MonteCarloRunner",
           "ReplaySession", "SCENARIOS", "Scenario", "SimulationEngine", "SimulationMetrics",
           "SimulationRecorder", "SimulationResult", "TICK_ORDER", "get_scenario", "load_log",
           "run_scenario"]
