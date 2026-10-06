import unittest

from simurg.safety.rta import Command, RuntimeAssurance, Source, VehicleState


def cruise(**kw):
    s = dict(alt_agl_m=150, airspeed_mps=28, bank_deg=0, pitch_deg=2,
             climb_mps=0, fence_dist_m=2000, fence_closing_mps=0)
    s.update(kw)
    return VehicleState(**s)


SAFE = Command(0, 3, 26)


class RtaTest(unittest.TestCase):
    def test_benign_command_passes(self):
        rta = RuntimeAssurance()
        cmd, src = rta.select(cruise(), Command(20, 2, 28), SAFE)
        self.assertIs(src, Source.ADVANCED)

    def test_steep_bank_command_switches_to_safety(self):
        rta = RuntimeAssurance()
        _, src = rta.select(cruise(), Command(70, 2, 28), SAFE)
        self.assertIs(src, Source.SAFETY)
        self.assertIn("asiri_yatis", rta.last_reasons)

    def test_fence_prediction(self):
        rta = RuntimeAssurance()
        _, src = rta.select(cruise(fence_dist_m=120, fence_closing_mps=28),
                            Command(0, 2, 28), SAFE)
        self.assertIs(src, Source.SAFETY)

    def test_hysteresis_and_recovery(self):
        rta = RuntimeAssurance(recovery_cycles=10)
        rta.select(cruise(), Command(70, 2, 28), SAFE)
        for i in range(9):
            _, src = rta.select(cruise(), Command(10, 2, 28), SAFE)
            self.assertIs(src, Source.SAFETY)
        _, src = rta.select(cruise(), Command(10, 2, 28), SAFE)
        self.assertIs(src, Source.ADVANCED)

    def test_hard_violation_latches(self):
        rta = RuntimeAssurance(recovery_cycles=1)
        rta.select(cruise(alt_agl_m=10), Command(0, 2, 28), SAFE)
        for _ in range(20):
            _, src = rta.select(cruise(), Command(0, 2, 28), SAFE)
        self.assertIs(src, Source.SAFETY)
        self.assertTrue(rta.latched)


if __name__ == "__main__":
    unittest.main()
