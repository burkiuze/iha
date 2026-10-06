import json
import math
import unittest

import numpy as np

from simurg.core.frames import (attitude_angles, cross3, quat_from_euler, quat_mul,
                                quat_to_dcm)
from simurg.core.types import VehicleState
from simurg.safety.rta import EnvelopeState
from simurg.sim.state import RigidBodyState


def vs(yaw=0.0, pitch=0.0, roll=0.0, pos=(0, 0, -100.0), vel=(20, 0, -1.0)):
    return VehicleState(1.5, np.array(pos, float), np.array(vel, float),
                        quat_from_euler(math.radians(yaw), math.radians(pitch), math.radians(roll)),
                        np.zeros(3), airspeed_mps=21.0, groundspeed_mps=20.0)


class FramesTest(unittest.TestCase):
    def test_hover_attitude_is_nose_up_with_heading(self):
        R = quat_to_dcm(quat_from_euler(math.radians(30), math.pi / 2, 0.0))
        h, p, b = attitude_angles(R)
        self.assertAlmostEqual(math.degrees(p), 90.0, places=6)
        self.assertAlmostEqual(math.degrees(h), 30.0, places=6)   # askıda da tanımlı
        self.assertAlmostEqual(b, 0.0, places=6)

    def test_cruise_attitude(self):
        h, p, b = attitude_angles(quat_to_dcm(quat_from_euler(math.radians(-45), 0.0,
                                                              math.radians(20))))
        self.assertAlmostEqual(math.degrees(h), -45.0, places=6)
        self.assertAlmostEqual(math.degrees(p), 0.0, places=6)
        self.assertAlmostEqual(math.degrees(b), 20.0, places=6)

    def test_bank_is_span_axis_inclination(self):
        # tanım: bank = asin(cos(pitch) * sin(roll)) — askıda da sürekli
        _, _, b = attitude_angles(quat_to_dcm(quat_from_euler(0.0, math.radians(30),
                                                              math.radians(20))))
        expect = math.asin(math.cos(math.radians(30)) * math.sin(math.radians(20)))
        self.assertAlmostEqual(b, expect, places=9)

    def test_dcm_orthonormal_and_quat_mul(self):
        q = quat_from_euler(0.3, -0.7, 1.1)
        R = quat_to_dcm(q)
        np.testing.assert_allclose(R @ R.T, np.eye(3), atol=1e-12)
        np.testing.assert_allclose(quat_to_dcm(quat_mul(q, q)), R @ R, atol=1e-12)

    def test_cross3_matches_numpy(self):
        rng = np.random.default_rng(0)
        for _ in range(20):
            a, b = rng.normal(size=3), rng.normal(size=3)
            np.testing.assert_allclose(cross3(a, b), np.cross(a, b), atol=1e-12)


class VehicleStateTest(unittest.TestCase):
    def test_derived_views(self):
        s = vs(yaw=10, pitch=0, roll=-15)
        self.assertAlmostEqual(s.altitude_m, 100.0)
        self.assertAlmostEqual(s.climb_mps, 1.0)
        h, p, b = s.attitude_deg
        self.assertAlmostEqual(h, 10.0, places=6)
        self.assertAlmostEqual(p, 0.0, places=6)
        self.assertAlmostEqual(b, -15.0, places=6)

    def test_snapshot_is_json_stable(self):
        snap = vs().snapshot()
        self.assertEqual(json.loads(json.dumps(snap)), snap)
        for key in ("t", "pos", "vel", "att_deg", "airspeed", "alt", "mode", "health"):
            self.assertIn(key, snap)

    def test_envelope_view_from_central_state(self):
        e = EnvelopeState.from_vehicle_state(vs(pitch=6, roll=25), 800.0, 3.0)
        self.assertAlmostEqual(e.alt_agl_m, 100.0)
        self.assertAlmostEqual(e.bank_deg, math.degrees(math.asin(
            math.cos(math.radians(6)) * math.sin(math.radians(25)))), places=6)
        self.assertAlmostEqual(e.pitch_deg, 6.0, places=6)
        self.assertEqual(e.airspeed_mps, 21.0)
        self.assertEqual((e.fence_dist_m, e.fence_closing_mps), (800.0, 3.0))

    def test_rigid_body_vector_roundtrip(self):
        rb = RigidBodyState(np.arange(3.0), np.arange(3.0) + 3, quat_from_euler(0.1, 0.2, 0.3),
                            np.array([0.1, -0.2, 0.3]))
        rb2 = RigidBodyState.from_vector(rb.to_vector())
        np.testing.assert_allclose(rb2.to_vector(), rb.to_vector())


if __name__ == "__main__":
    unittest.main()
