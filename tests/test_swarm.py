import unittest

import numpy as np

from simurg.swarm.auction import Agent, Task, allocate, route_energy_wh


class SwarmTest(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(3)
        self.base = np.zeros(2)
        self.agents = [Agent(f"S{i}", np.array([0.0, 100.0 * i]), e)
                       for i, e in enumerate([900, 900, 300])]
        self.tasks = [Task(f"T{j:02d}", rng.uniform(-15000, 15000, 2),
                           priority=1 + (j % 3)) for j in range(15)]

    def test_each_task_at_most_once_and_energy_feasible(self):
        res = allocate(self.agents, self.tasks, self.base)
        flat = [t for r in res.values() for t in r]
        self.assertEqual(len(flat), len(set(flat)))
        by_id = {t.id: t for t in self.tasks}
        for a in self.agents:
            e = route_energy_wh(a, [by_id[t] for t in res[a.id]], self.base)
            self.assertLessEqual(e, a.energy_wh * (1 - a.reserve) + 1e-9)

    def test_deterministic(self):
        r1 = allocate(self.agents, self.tasks, self.base)
        r2 = allocate(self.agents, self.tasks, self.base)
        self.assertEqual(r1, r2)

    def test_load_spreads_across_capable_agents(self):
        res = allocate(self.agents, self.tasks, self.base)
        self.assertGreater(len(res["S0"]), 0)
        self.assertGreater(len(res["S1"]), 0)

    def test_unreachable_task_left_unassigned(self):
        far = Task("FAR", np.array([1e6, 0.0]))
        res = allocate(self.agents, [far], self.base)
        self.assertTrue(all("FAR" not in r for r in res.values()))


if __name__ == "__main__":
    unittest.main()
