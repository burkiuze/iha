import unittest
from dataclasses import replace

from simurg.core.config import EnvironmentConfig
from simurg.core.events import EventType
from simurg.sim import Expectations, MissionProfile, MonteCarloRunner, Scenario
from simurg.sim.montecarlo import choice, normal, uniform


def hover_factory(seed, p):
    """Kısa senaryo: kalkış + ileri geçiş başlangıcı (25 s)."""
    return Scenario("mc_hover", duration_s=25.0, seed=seed,
                    mission=MissionProfile(waypoints=((500.0, 0.0),)),
                    environment=EnvironmentConfig(wind_ned_mps=(p["wind"], 0.0, 0.0),
                                                  turbulence_std_mps=p["turb"]),
                    expectations=Expectations(forbidden_events=(EventType.IMPACT,)))


def failing_factory(seed, p):
    sc = hover_factory(seed, p)
    exp = Expectations(required_events=(EventType.MISSION_COMPLETE,)) if p["flag"] > 0.5 \
        else sc.expectations
    return replace(sc, expectations=exp)


DISTS = {"wind": uniform(-3, 3), "turb": uniform(0, 0.8)}


class MonteCarloTest(unittest.TestCase):
    def test_seeds_and_params_are_reproducible(self):
        a = MonteCarloRunner(hover_factory, 4, base_seed=5, distributions=DISTS)
        b = MonteCarloRunner(hover_factory, 4, base_seed=5, distributions=DISTS)
        self.assertEqual(a.seeds(), b.seeds())
        self.assertEqual(len(set(a.seeds())), 4)
        s = a.seeds()[2]
        self.assertEqual(a.sample_params(s), b.sample_params(s))
        self.assertNotEqual(a.seeds(), MonteCarloRunner(hover_factory, 4, 6, DISTS).seeds())

    def test_campaign_and_reproduction(self):
        runner = MonteCarloRunner(failing_factory, 3, base_seed=1,
                                  distributions={**DISTS, "flag": uniform(0, 1)})
        rep = runner.run()
        self.assertEqual(rep.success_count + rep.failure_count, 3)
        flagged = [r.seed for r in rep.runs if r.params["flag"] > 0.5]
        self.assertEqual(rep.failed_seeds, flagged)
        self.assertEqual(len(rep.runs), 3)
        dist = rep.metric_distribution("energy_consumed_wh")
        self.assertEqual(dist["n"], 3)
        self.assertLessEqual(dist["min"], dist["mean"])
        # ilk koşuyu yalnızca tohumuyla yeniden üret: metrikler birebir aynı
        first = rep.runs[0]
        again = runner.reproduce(first.seed)
        self.assertEqual(again.metrics.to_dict(), first.metrics)
        self.assertEqual(again.passed, first.passed)
        d = rep.to_dict()
        self.assertEqual(d["failed_seeds"], rep.failed_seeds)

    def test_distribution_helpers(self):
        import numpy as np
        rng = np.random.default_rng(0)
        self.assertTrue(-1 <= uniform(-1, 1)(rng) <= 1)
        self.assertIn(choice(2.0, 4.0)(rng), (2.0, 4.0))
        self.assertIsInstance(normal(0, 1)(rng), float)
        with self.assertRaises(ValueError):
            MonteCarloRunner(hover_factory, 0)


if __name__ == "__main__":
    unittest.main()
