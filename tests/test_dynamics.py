import math
import unittest

import numpy as np

from simurg.aero import AeroInputs, AnalyticAeroModel, Table1D, Table2D, TableAeroModel
from simurg.core.config import VehicleConfig
from simurg.core.errors import ConfigurationError, SimulationError
from simurg.core.frames import quat_from_euler
from simurg.sim.dynamics import (EulerIntegrator, MassProperties, RigidBodyDynamics,
                                 RK4Integrator, Wrench, integrate, make_integrator)
from simurg.sim.propulsion import PropulsionModel

V = VehicleConfig()
DYN = RigidBodyDynamics(MassProperties.from_vehicle(V))


def x0(q=None, omega=(0, 0, 0), vel=(0, 0, 0)):
    q = quat_from_euler(0, math.pi / 2, 0) if q is None else q
    return np.concatenate([[0, 0, -100.0], vel, q, omega]).astype(float)


def zero_wrench(_):
    return Wrench(np.zeros(3), np.zeros(3), np.zeros(3))


class DynamicsTest(unittest.TestCase):
    def test_free_fall(self):
        d = DYN.derivative(x0(), zero_wrench(None))
        np.testing.assert_allclose(d[3:6], [0, 0, 9.80665])

    def test_hover_thrust_balances_weight(self):
        # askıda burun yukarı: itki gövde x ekseninde
        w = Wrench(np.array([V.weight_n, 0, 0]), np.zeros(3), np.zeros(3))
        np.testing.assert_allclose(DYN.derivative(x0(), w)[3:6], 0.0, atol=1e-9)

    def test_torque_free_rotation_preserves_energy(self):
        x = x0(omega=(0.5, 0.0, 0.3))
        J = V.inertia
        e0 = x[10:13] @ J @ x[10:13]
        for integ in (RK4Integrator(), EulerIntegrator()):
            xs = x.copy()
            for _ in range(200):
                xs = integrate(DYN, zero_wrench, integ, xs, 0.01)
            self.assertAlmostEqual(float(np.linalg.norm(xs[6:10])), 1.0, places=9)
            e = xs[10:13] @ J @ xs[10:13]
            tol = 1e-6 if integ.name == "rk4" else 0.05
            self.assertAlmostEqual(e / e0, 1.0, delta=tol)

    def test_rk4_more_accurate_than_euler(self):
        exact_z = -100.0 + 0.5 * 9.80665 * 1.0
        res = {}
        for integ in (RK4Integrator(), EulerIntegrator()):
            x = x0()
            for _ in range(10):
                x = integrate(DYN, zero_wrench, integ, x, 0.1)
            res[integ.name] = abs(x[2] - exact_z)
        self.assertLess(res["rk4"], 1e-9)
        self.assertGreater(res["euler"], 0.1)

    def test_integrator_registry_and_nan_guard(self):
        self.assertEqual(make_integrator("rk4").name, "rk4")
        with self.assertRaises(ConfigurationError):
            make_integrator("yok")
        bad = lambda _: Wrench(np.array([np.nan, 0, 0]), np.zeros(3), np.zeros(3))  # noqa: E731
        with self.assertRaises(SimulationError):
            integrate(DYN, bad, RK4Integrator(), x0(), 0.01)


class PropulsionTest(unittest.TestCase):
    def test_thrust_lapse_and_power(self):
        p = PropulsionModel(V)
        self.assertEqual(p.thrust_scale(0.0), 1.0)
        self.assertLess(p.thrust_scale(28.0), 0.6)
        thr = p.thrusts(np.full(8, 0.62), 0.0)
        self.assertAlmostEqual(float(thr.sum()), 8 * 49 * 0.62)
        hover_kw = p.electrical_power(np.full(8, V.weight_n / 8), 0.0, 1.225) / 1000
        self.assertTrue(3.0 < hover_kw < 5.0, hover_kw)

    def test_symmetric_thrust_gives_no_moment(self):
        f, m = PropulsionModel(V).wrench_body(np.full(8, 30.0), np.zeros(4))
        np.testing.assert_allclose(m, 0.0, atol=1e-9)
        self.assertAlmostEqual(f[0], 240.0)


def aero_in(alpha_deg=4.0, V=24.0, defl=(0, 0, 0, 0)):
    a = math.radians(alpha_deg)
    return AeroInputs(np.array([V * math.cos(a), 0.0, V * math.sin(a)]), np.zeros(3),
                      np.array(defl, float), 1.225, np.array([-0.8, 0.8, -0.8, 0.8]), -0.35,
                      0.04, 2.0)


class AeroTest(unittest.TestCase):
    def test_zero_airspeed_no_force(self):
        out = AnalyticAeroModel().evaluate(aero_in(V=0.0))
        np.testing.assert_allclose(out.force_body, 0.0)

    def test_cruise_lift_and_drag_signs(self):
        out = AnalyticAeroModel().evaluate(aero_in(4.0, 24.0))
        v = aero_in(4.0, 24.0).v_air_body
        self.assertLess(out.force_body[2], -150.0)                # taşıma yukarı (-b_z)
        self.assertLess(float(np.dot(out.force_body, v)), 0.0)   # sürükleme hıza karşı
        self.assertGreater(out.cl / out.cd, 10.0)

    def test_full_range_alpha_is_finite(self):
        m = AnalyticAeroModel()
        for a in range(-180, 181, 15):
            o = m.evaluate(aero_in(a, 15.0))
            self.assertTrue(np.all(np.isfinite(o.force_body)))

    def test_elevon_collective_pitch_and_differential_roll(self):
        m = AnalyticAeroModel()
        base = m.evaluate(aero_in())
        col = m.evaluate(aero_in(defl=(0.2, 0.2, 0.2, 0.2)))
        dif = m.evaluate(aero_in(defl=(0.2, -0.2, 0.2, -0.2)))
        self.assertLess(col.moment_body[1] - base.moment_body[1], 0.0)   # arka elevon: burun aşağı
        self.assertNotAlmostEqual(dif.moment_body[0], base.moment_body[0])

    def test_table_model_matches_analytic_on_grid(self):
        an = AnalyticAeroModel()
        grid = np.radians(np.arange(-180, 181, 1.0))
        tab = TableAeroModel.from_model(an, grid)
        for a in (-30.0, 0.0, 4.0, 12.0, 45.0, 90.0):
            o1, o2 = an.evaluate(aero_in(a)), tab.evaluate(aero_in(a))
            np.testing.assert_allclose(o2.force_body, o1.force_body, rtol=1e-6, atol=1e-6)

    def test_lookup_tables(self):
        t = Table1D(np.array([0.0, 1.0, 2.0]), np.array([0.0, 10.0, 0.0]))
        self.assertEqual(t(0.5), 5.0)
        self.assertEqual(t(5.0), 0.0)                 # kırpma
        self.assertFalse(t.in_range(5.0))
        t2 = Table2D(np.array([0.0, 1.0]), np.array([0.0, 1.0]), np.array([[0.0, 1.0], [2.0, 3.0]]))
        self.assertAlmostEqual(t2(0.5, 0.5), 1.5)
        with self.assertRaises(ConfigurationError):
            Table1D(np.array([1.0, 0.0]), np.array([0.0, 1.0]))


if __name__ == "__main__":
    unittest.main()
