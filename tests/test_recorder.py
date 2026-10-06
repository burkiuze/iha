import json
import tempfile
import unittest
from pathlib import Path

from simurg.core.errors import SimulationError
from simurg.core.events import EventBus, EventType
from simurg.sim.recorder import SCHEMA, SCHEMA_VERSION, SimulationRecorder, jsonable, load_log

try:                                   # python -m unittest tests.test_x
    from ._simcache import scenario_result
except ImportError:                    # python -m unittest discover -s tests
    from _simcache import scenario_result


class RecorderUnitTest(unittest.TestCase):
    def test_events_never_dropped_and_snapshots_periodic(self):
        bus = EventBus()
        rec = SimulationRecorder(bus, snapshot_period_s=1.0, meta={"name": "x"})
        for k in range(100):
            t = k * 0.02
            bus.publish(EventType.FDIR_WARNING, t, "test", "", k=k)
            rec.maybe_snapshot(t, {"t": t})
        self.assertEqual(len(rec.events), 100)
        self.assertEqual([s["t"] for s in rec.snapshots], [0.0, 1.0])
        self.assertEqual([e["seq"] for e in rec.events], list(range(100)))

    def test_jsonable_handles_numpy_and_nan(self):
        import numpy as np
        out = jsonable({"a": np.float64(1.5), "b": np.array([1, 2]), "c": float("nan"),
                        "d": np.bool_(True), "e": EventType.LINK_LOST})
        self.assertEqual(out, {"a": 1.5, "b": [1, 2], "c": None, "d": True, "e": "link_lost"})


class RecorderInSimulationTest(unittest.TestCase):
    def test_schema_and_json_roundtrip(self):
        r = scenario_result("combined_degraded")
        log = r.log
        self.assertEqual((log["schema"], log["schema_version"]), (SCHEMA, SCHEMA_VERSION))
        self.assertEqual(set(log), {"schema", "schema_version", "meta", "events", "snapshots", "metrics"})
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "log.json"
            p.write_text(json.dumps(log), encoding="utf-8")
            self.assertEqual(load_log(p), json.loads(json.dumps(log)))
        self.assertEqual(log["metrics"]["final_mode"], r.metrics.final_mode)
        self.assertIn("aero_provenance", log["meta"])

    def test_important_events_recorded(self):
        types = {e["type"] for e in scenario_result("combined_degraded").events}
        for t in ("sim_started", "fault_injected", "fault_cleared", "mode_transition",
                  "fdir_warning", "nav_source_rejected", "link_lost", "link_restored",
                  "transition_started", "transition_completed", "touchdown", "sim_finished"):
            self.assertIn(t, types)

    def test_load_rejects_unknown_schema(self):
        with self.assertRaises(SimulationError):
            load_log({"schema": "baska", "schema_version": 1})
        with self.assertRaises(SimulationError):
            load_log({"schema": SCHEMA, "schema_version": 99})


if __name__ == "__main__":
    unittest.main()
