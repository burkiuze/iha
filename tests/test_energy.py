import unittest

from simurg.power.energy_manager import EnergyManager


def profile(t):
    if t < 45:
        return 3800.0       # VTOL kalkış
    if t < 60:
        return 1500.0       # geçiş
    if 3000 <= t < 3002:
        return 1490.0       # rüzgâr hamlesi
    return 590.0            # seyir


class EnergyTest(unittest.TestCase):
    def test_bus_balance_and_no_brownout(self):
        em = EnergyManager()
        t, dt = 0.0, 0.1
        while t < 3600:
            s = em.step(dt, profile(t), solar_w=80.0)
            self.assertAlmostEqual(s.bus_balance_w, 0.0, places=6)
            self.assertEqual(s.unmet_w, 0.0)
            t += dt

    def test_fuel_cell_slew_limited(self):
        em = EnergyManager()
        prev = em.fc_w
        for _ in range(200):
            em.step(0.1, 3800.0)
            self.assertLessEqual(em.fc_w - prev, em.cfg.fc_slew_w_per_s * 0.1 + 1e-9)
            prev = em.fc_w

    def test_supercap_absorbs_step(self):
        em = EnergyManager()
        for _ in range(600):
            em.step(0.1, 590.0)
        s = em.step(0.1, 2500.0)
        self.assertGreater(s.sc_w, 0.0)

    def test_endurance_hydrogen_phase_without_solar(self):
        em = EnergyManager()
        t, dt = 0.0, 1.0
        while em.h2_wh > 0 and t < 10 * 3600:
            em.step(dt, profile(t))
            t += dt
        self.assertGreater(t / 3600, 3.2)
        self.assertGreater(em.batt_soc, 0.6)   # SoC regülasyonu çalışıyor

    def test_return_home_decision(self):
        em = EnergyManager()
        self.assertTrue(em.return_home_feasible(20_000, 25, 590))
        em.h2_wh = 0.0
        em.batt_soc = 0.3
        self.assertFalse(em.return_home_feasible(40_000, 25, 590))


if __name__ == "__main__":
    unittest.main()
