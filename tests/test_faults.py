import unittest

import numpy as np

from simurg.core.errors import InvalidScenarioError
from simurg.core.events import EventBus, EventLog, EventType
from simurg.power.energy_manager import EnergyManager
from simurg.sim.faults import (ControllerFaultTarget, EnergyFaultTarget, Fault, FaultInjector,
                               FaultKind, FaultSchedule)
from simurg.sim.link import LinkModel
from simurg.sim.sensors import SensorModel, SensorSuite


class Recorder:
    def __init__(self):
        self.calls = []

    def apply_fault(self, f):
        self.calls.append(("apply", f.id))

    def clear_fault(self, f):
        self.calls.append(("clear", f.id))


class ScheduleTest(unittest.TestCase):
    def test_validation(self):
        with self.assertRaises(InvalidScenarioError):
            FaultSchedule((Fault("a", FaultKind.LINK_LOSS, "link:c2", 1.0),
                           Fault("a", FaultKind.LINK_LOSS, "link:c2", 2.0)))
        with self.assertRaises(InvalidScenarioError):
            FaultSchedule((Fault("a", FaultKind.LINK_LOSS, "sensor:GNSS", 1.0),))
        with self.assertRaises(InvalidScenarioError):
            FaultSchedule((Fault("a", FaultKind.LINK_LOSS, "link:c2", -1.0),))
        with self.assertRaises(InvalidScenarioError):
            FaultSchedule((Fault("a", FaultKind.SENSOR_BIAS, "sensor:GNSS", 1.0, severity=2.0),))

    def test_sorted_by_start_then_id(self):
        s = FaultSchedule((Fault("b", FaultKind.LINK_LOSS, "link:c2", 5.0),
                           Fault("a", FaultKind.LINK_LOSS, "link:c2", 5.0),
                           Fault("c", FaultKind.LINK_LOSS, "link:c2", 1.0)))
        self.assertEqual([f.id for f in s], ["c", "a", "b"])


class InjectorTest(unittest.TestCase):
    def _run(self):
        bus = EventBus()
        log = EventLog(bus)
        tgt = Recorder()
        sched = FaultSchedule((Fault("F1", FaultKind.LINK_LOSS, "link:c2", 0.05, 0.1),
                               Fault("F2", FaultKind.LINK_LOSS, "link:c2", 0.1)))
        inj = FaultInjector(sched, {"link": tgt}, bus)
        for k in range(20):
            inj.update(round(k * 0.02, 9))
        return inj, tgt, log

    def test_activation_on_first_tick_at_or_after_start(self):
        inj, tgt, log = self._run()
        self.assertEqual(inj.activation_times, {"F1": 0.06, "F2": 0.1})
        self.assertEqual(tgt.calls, [("apply", "F1"), ("apply", "F2"), ("clear", "F1")])
        types = [e.type for e in log.events]
        self.assertEqual(types, [EventType.FAULT_INJECTED, EventType.FAULT_INJECTED,
                                 EventType.FAULT_CLEARED])
        self.assertEqual(log.events[2].time_s, 0.16)

    def test_reproducible(self):
        a, b = self._run(), self._run()
        self.assertEqual(a[0].activation_times, b[0].activation_times)
        self.assertEqual([e.to_dict() for e in a[2].events], [e.to_dict() for e in b[2].events])

    def test_missing_target_system(self):
        with self.assertRaises(InvalidScenarioError):
            FaultInjector(FaultSchedule((Fault("F", FaultKind.LINK_LOSS, "link:c2", 0.0),)), {})


class TargetsTest(unittest.TestCase):
    def test_energy_target(self):
        em = EnergyManager()
        t = EnergyFaultTarget(em)
        fc = Fault("a", FaultKind.ENERGY_FC_DEGRADED, "energy:fc", 0.0, severity=0.5)
        fade = Fault("b", FaultKind.ENERGY_BATTERY_FADE, "energy:battery", 0.0, severity=0.3)
        lim = Fault("c", FaultKind.ENERGY_POWER_LIMIT, "energy:bus", 0.0, severity=0.75)
        for f in (fc, fade, lim):
            t.apply_fault(f)
        self.assertEqual((em.fc_max_w, em.batt_capacity_scale), (400.0, 0.7))
        self.assertEqual((em.batt_discharge_scale, em.sc_power_scale), (0.25, 0.25))
        for f in (fc, fade, lim):
            t.clear_fault(f)
        self.assertEqual(em.fc_power_scale, 1.0)
        self.assertEqual(em.batt_capacity_scale, 0.7)      # kapasite kaybı kalıcı
        self.assertEqual(em.sc_power_scale, 1.0)

    def test_controller_and_link_targets(self):
        class G:
            fault_bank_deg = None
        g = G()
        t = ControllerFaultTarget(g)
        f = Fault("a", FaultKind.CONTROLLER_FAULT, "controller:advanced", 0.0)
        t.apply_fault(f)
        self.assertEqual(g.fault_bank_deg, 75.0)
        t.clear_fault(f)
        self.assertIsNone(g.fault_bank_deg)
        link = LinkModel()
        lf = Fault("l", FaultKind.LINK_LOSS, "link:c2", 0.0)
        link.apply_fault(lf)
        self.assertEqual(link.update(1.0), (False, 0.0))
        self.assertEqual(link.update(4.5), (False, 3.5))
        link.clear_fault(lf)
        self.assertEqual(link.update(5.0), (True, 0.0))


class SensorTest(unittest.TestCase):
    def test_same_seed_same_measurements_and_dropout_keeps_stream(self):
        def series(drop):
            s = SensorModel("GNSS", [3.0, 3.0], np.random.default_rng(9))
            out = []
            for k in range(10):
                if drop and k == 3:
                    s.apply_fault(Fault("d", FaultKind.SENSOR_DROPOUT, "sensor:GNSS", 0.0))
                if drop and k == 6:
                    s.clear_fault(Fault("d", FaultKind.SENSOR_DROPOUT, "sensor:GNSS", 0.0))
                out.append(s.measure(np.zeros(2), k))
            return out
        a, b = series(False), series(True)
        self.assertFalse(b[4].valid)
        np.testing.assert_array_equal(a[8].value, b[8].value)   # RNG akışı arızadan etkilenmez

    def test_bias_and_suite_routing(self):
        s = SensorModel("VIO", [1.0, 1.0], np.random.default_rng(0))
        suite = SensorSuite([s])
        suite.apply_fault(Fault("b", FaultKind.SENSOR_BIAS, "sensor:VIO", 0.0,
                                params={"bias": [100.0, 0.0]}))
        m = np.mean([s.measure(np.zeros(2), 0).value for _ in range(200)], axis=0)
        self.assertAlmostEqual(m[0], 100.0, delta=0.5)
        with self.assertRaises(InvalidScenarioError):
            suite.apply_fault(Fault("x", FaultKind.SENSOR_DROPOUT, "sensor:YOK", 0.0))


if __name__ == "__main__":
    unittest.main()
