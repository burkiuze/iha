import unittest

import numpy as np

from simurg.config import WEIGHT_N, hover_effectiveness
from simurg.control.allocation import ControlAllocator, ScheduledAllocator
from simurg.control.effectiveness import (CRUISE_AXIS_WEIGHTS, HOVER_AXIS_WEIGHTS,
                                          EffectivenessConditions, HoverEffectiveness,
                                          ScheduledEffectiveness, alloc_to_body, blend_sigma,
                                          body_to_alloc)
from simurg.control.transition import TransitionCoordinator, TransitionPhase


class EffectivenessTest(unittest.TestCase):
    def test_hover_regime_identical_to_legacy(self):
        B, lo, hi = hover_effectiveness()
        r = ScheduledEffectiveness().regime(EffectivenessConditions(airspeed_mps=0.0))
        np.testing.assert_allclose(r.B, B)
        np.testing.assert_allclose(r.lower, lo)
        np.testing.assert_allclose(r.upper, hi)
        np.testing.assert_allclose(r.axis_weights, HOVER_AXIS_WEIGHTS)

    def test_scheduled_allocator_matches_legacy_in_hover(self):
        v = [WEIGHT_N, 2.0, -1.0, 0.5]
        a = ControlAllocator(*hover_effectiveness()).allocate(v)
        b = ScheduledAllocator(HoverEffectiveness()).allocate(v)
        np.testing.assert_allclose(a.u, b.u)

    def test_cruise_regime_folds_inner_motors_and_boosts_elevons(self):
        hover = ScheduledEffectiveness().regime(EffectivenessConditions(0.0))
        cruise = ScheduledEffectiveness().regime(EffectivenessConditions(
            28.0, thrust_scale=0.5, fold_inner_motors=True))
        self.assertEqual(cruise.name, "cruise")
        folded = [1, 2, 5, 6]
        np.testing.assert_allclose(cruise.B[:, folded], 0.0)
        np.testing.assert_allclose(cruise.upper[folded], 0.0)
        self.assertGreater(abs(cruise.B[3, 8]), 2 * abs(hover.B[3, 8]))
        np.testing.assert_allclose(cruise.axis_weights, CRUISE_AXIS_WEIGHTS)

    def test_sigma_and_frame_mapping(self):
        self.assertEqual((blend_sigma(0), blend_sigma(12.5), blend_sigma(30)), (0.0, 0.5, 1.0))
        T, M = alloc_to_body(body_to_alloc(100.0, np.array([1.0, 2.0, 3.0])))
        self.assertEqual(T, 100.0)
        np.testing.assert_allclose(M, [1.0, 2.0, 3.0])


class TransitionTest(unittest.TestCase):
    def test_forward_completes(self):
        tc = TransitionCoordinator()
        tc.start_forward(0.0, 50.0)
        st, t, V = None, 0.0, 0.0
        while tc.active and t < 30:
            t += 0.02
            V = min(V + 0.1, 25.0)
            st = tc.update(t, 0.02, V, tc._pitch_cmd, 50.0, 0.0)
        self.assertIs(st.phase, TransitionPhase.COMPLETED)
        self.assertTrue(st.just_finished)
        self.assertLessEqual(st.pitch_cmd_deg, 20.0)

    def test_abort_on_altitude_loss_and_timeout(self):
        tc = TransitionCoordinator()
        tc.start_forward(0.0, 50.0)
        st = tc.update(0.02, 0.02, 5.0, 88.0, 38.0, 0.0)
        self.assertEqual((st.phase, st.abort_reason), (TransitionPhase.ABORTED, "irtifa_kaybi"))
        tc.start_forward(0.0, 50.0)
        st = tc.update(25.0, 0.02, 5.0, 60.0, 50.0, 0.0)
        self.assertEqual(st.abort_reason, "zaman_asimi")

    def test_abort_on_persistent_saturation(self):
        tc = TransitionCoordinator()
        tc.start_forward(0.0, 50.0)
        st, t = None, 0.0
        while tc.active:
            t += 0.02
            st = tc.update(t, 0.02, 8.0, tc._pitch_cmd, 50.0, 0.9)
        self.assertEqual(st.abort_reason, "eyleyici_doymasi")
        self.assertAlmostEqual(t, 1.52, delta=0.05)

    def test_back_transition(self):
        tc = TransitionCoordinator()
        tc.start_back(0.0, 100.0, 5.0)
        st = tc.update(0.02, 0.02, 4.0, 85.0, 100.0, 0.0)
        self.assertIs(st.phase, TransitionPhase.COMPLETED)


if __name__ == "__main__":
    unittest.main()
