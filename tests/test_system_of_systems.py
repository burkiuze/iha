"""Ölçüm hattı, aşamalı komut doğrulama, üçlü FCC, FDIR raporları, kayıt kanalları
ve bunlara bağlı güvenlik değişmezleri."""

import math
import unittest

import numpy as np

from simurg.control.allocation import ControlAllocator
from simurg.control.effectiveness import HoverEffectiveness
from simurg.core.events import EventType
from simurg.core.types import HealthState, SensorMeasurement
from simurg.fdir.lanes import LaneOutput, LaneState, TriplexVoter
from simurg.safety.command_validator import CommandProposal, CommandValidator, RejectClass
from simurg.safety.rta import Command
from simurg.sensing import ChannelSpec, SensorChannel, SensorPipeline, Validity
from simurg.sim.recorder import CHANNEL_OF, RECORDER_CHANNELS
from simurg.sim.replay import ReplaySession

try:
    from ._simcache import scenario_result
except ImportError:
    from _simcache import scenario_result


def raw(v, t, valid=True, quality=1.0, health=1.0, sid="BARO"):
    return SensorMeasurement(sid, t, np.atleast_1d(np.asarray(v, float)), np.eye(1), valid,
                             quality, health)


class MeasurementPipelineTest(unittest.TestCase):
    def test_channel_is_unknown_until_first_measurement(self):
        ch = SensorChannel("BARO")
        self.assertIs(ch.health, HealthState.UNKNOWN)
        m, change = ch.process(raw(100.0, 0.0), 0.0)
        self.assertIs(ch.health, HealthState.NOMINAL)
        self.assertEqual(change.previous, HealthState.UNKNOWN)
        self.assertTrue(m.usable)

    def test_measurement_carries_full_metadata(self):
        m, _ = SensorChannel("BARO").process(raw(100.0, 1.0, quality=0.8), 1.05)
        d = m.to_dict()
        for k in ("source", "timestamp", "validity", "freshness_s", "quality", "health",
                  "confidence"):
            self.assertIn(k, d)
        self.assertAlmostEqual(m.freshness_s, 0.05)
        self.assertAlmostEqual(m.confidence, 0.8)

    def test_invalid_measurement_degrades_then_fails_with_zero_confidence(self):
        ch = SensorChannel("BARO", ChannelSpec(fail_after=3))
        ch.process(raw(100.0, 0.0), 0.0)
        states = []
        for k in range(1, 4):
            m, _ = ch.process(raw(math.nan, k * 0.02), k * 0.02)
            states.append(ch.health)
            self.assertIs(m.validity, Validity.INVALID)
            self.assertEqual(m.confidence, 0.0)
            self.assertFalse(m.usable)
        self.assertEqual(states, [HealthState.DEGRADED, HealthState.DEGRADED, HealthState.FAILED])

    def test_stale_and_future_timestamps_are_rejected(self):
        ch = SensorChannel("BARO", ChannelSpec(max_age_s=0.1))
        self.assertIs(ch.process(raw(1.0, 0.0), 0.5)[0].validity, Validity.STALE)
        self.assertIs(ch.process(raw(1.0, 2.0), 1.0)[0].validity, Validity.STALE)

    def test_plausibility_range_and_rate(self):
        ch = SensorChannel("BARO", ChannelSpec(lower=-10, upper=100, max_rate_per_s=50))
        self.assertIs(ch.process(raw(500.0, 0.0), 0.0)[0].validity, Validity.IMPLAUSIBLE)
        ch.process(raw(10.0, 0.1), 0.1)
        self.assertIs(ch.process(raw(30.0, 0.2), 0.2)[0].validity, Validity.IMPLAUSIBLE)
        self.assertIs(ch.process(raw(14.0, 0.3), 0.3)[0].validity, Validity.VALID)

    def test_silent_source_goes_stale_on_bus(self):
        p = SensorPipeline({"BARO": ChannelSpec(max_age_s=0.1, fail_after=2)})
        p.process(raw(5.0, 0.0), 0.0)
        p.check_freshness(0.5)
        p.check_freshness(0.6)
        self.assertIs(p.health()["BARO"], HealthState.FAILED)
        self.assertIs(p.bus.latest("BARO").validity, Validity.STALE)

    def test_pipeline_only_observes_and_keeps_simulation_deterministic(self):
        a, b = scenario_result("nominal"), scenario_result("nominal", 0)
        self.assertEqual(a.log["snapshots"], b.log["snapshots"])
        first = [e for e in a.events if e["type"] == EventType.SENSOR_HEALTH_CHANGED.value]
        self.assertTrue(all(e["data"]["state"] == "nominal" for e in first))


class StagedCommandValidationTest(unittest.TestCase):
    v = CommandValidator()

    def prop(self, **kw):
        base = dict(command=Command(10.0, 2.0, 24.0), source="mission_guidance", timestamp=10.0,
                    mode="MISSION")
        base.update(kw)
        return CommandProposal(**base)

    def check(self, p, now=10.0, mode="MISSION"):
        return self.v.validate(p, now=now, mode=mode)

    def test_valid_proposal_passes_all_stages(self):
        r = self.check(self.prop())
        self.assertTrue(r.accepted)
        self.assertEqual(r.command, Command(10.0, 2.0, 24.0))

    def test_each_reject_class(self):
        cases = [
            (self.prop(command="sola dön"), {}, RejectClass.INVALID, "schema"),
            (self.prop(command=Command(math.inf, 0, 24)), {}, RejectClass.INVALID, "schema"),
            (self.prop(timestamp=9.5), {}, RejectClass.STALE, "freshness"),
            (self.prop(timestamp=10.5), {}, RejectClass.STALE, "freshness"),
            (self.prop(), dict(now=None), RejectClass.STALE, "freshness"),
            (self.prop(mode="CRUISE"), {}, RejectClass.INCOMPATIBLE, "mode_compatibility"),
            (self.prop(mode="VTOL_LAND"), dict(mode="VTOL_LAND"), RejectClass.INCOMPATIBLE,
             "mode_compatibility"),
            (self.prop(command=Command(120.0, 0, 24)), {}, RejectClass.INVALID, "bounds"),
            (self.prop(source="unknown_box"), {}, RejectClass.UNKNOWN, "authority"),
            (self.prop(kind="actuator_direct"), {}, RejectClass.UNAUTHORIZED, "authority"),
        ]
        for p, kw, cat, stage in cases:
            with self.subTest(stage=stage, cat=cat):
                r = self.check(p, **kw)
                self.assertFalse(r.accepted)
                self.assertIsNone(r.command)
                self.assertIs(r.category, cat)
                self.assertEqual(r.stage, stage)

    def test_stale_mission_computer_proposals_never_reach_rta(self):
        r = scenario_result("mission_computer_failure")
        self.assertTrue(r.passed, r.expectation_failures)
        rej = [e for e in r.events if e["type"] == EventType.COMMAND_REJECTED.value]
        self.assertEqual([e["data"]["category"] for e in rej], ["stale"])
        self.assertEqual(r.metrics.rta_interventions, 0)
        why = ReplaySession.from_source(r).why_command_rejected()
        self.assertEqual(why[0]["stage"], "freshness")
        self.assertGreaterEqual(why[0]["age_s"], 0.1)


class TriplexLaneTest(unittest.TestCase):
    @staticmethod
    def outs(a, b, c, hb=(True, True, True)):
        return [LaneOutput(l, None if v is None else np.array([v], float), 0.0, h)
                for l, v, h in zip("ABC", (a, b, c), hb)]

    def test_single_divergent_lane_never_reaches_output_and_is_isolated(self):
        v = TriplexVoter(tol=0.05, persistence=3)
        for _ in range(3):
            r = v.vote(self.outs(0.5, 0.9, 0.5), None)
            self.assertAlmostEqual(float(r.output[0]), 0.5)
        self.assertIs(v.states["B"], LaneState.ISOLATED)
        self.assertEqual(v.available, ("A", "C"))

    def test_isolated_lane_cannot_rejoin_voter_as_nominal(self):
        v = TriplexVoter(tol=0.05, persistence=2)
        for _ in range(2):
            v.vote(self.outs(0.5, 0.9, 0.5), None)
        for _ in range(10):
            r = v.vote(self.outs(0.5, 0.5, 0.5), None)
            self.assertNotIn("B", r.voters)
        self.assertIs(v.states["B"], LaneState.ISOLATED)

    def test_heartbeat_loss_fails_lane_after_watchdog_timeout(self):
        v = TriplexVoter(heartbeat_timeout=3)
        seen = []
        for _ in range(3):
            r = v.vote(self.outs(None, 0.4, 0.4, hb=(False, True, True)), None)
            seen.append(v.states["A"])
            self.assertAlmostEqual(float(r.output[0]), 0.4)
        self.assertEqual(seen, [LaneState.DEGRADED, LaneState.DEGRADED, LaneState.FAILED])
        self.assertEqual(r.configuration, "duplex")

    def test_lanes_are_unknown_before_first_output(self):
        self.assertTrue(all(s is LaneState.UNKNOWN for s in TriplexVoter().states.values()))

    def test_duplex_disagreement_follows_last_good_output_and_isolates_outlier(self):
        v = TriplexVoter(tol=0.05, persistence=2, heartbeat_timeout=1)
        v.vote(self.outs(None, 0.5, 0.5, hb=(False, True, True)), None)
        last = np.array([0.5])
        for _ in range(2):
            r = v.vote(self.outs(None, 0.5, 0.95, hb=(False, True, True)), last)
            self.assertTrue(r.disagreement)
            self.assertAlmostEqual(float(r.output[0]), 0.5)
        self.assertIs(v.states["C"], LaneState.ISOLATED)

    def test_no_lane_means_no_output(self):
        v = TriplexVoter(heartbeat_timeout=1)
        r = v.vote(self.outs(None, None, None, hb=(False, False, False)), None)
        self.assertIsNone(r.output)
        self.assertEqual(r.configuration, "none")

    def test_lane_faults_in_simulation_are_masked_and_explained(self):
        for name, lane, state in (("fcc_lane_divergence", "B", "isolated"),
                                  ("fcc_lane_loss", "A", "failed")):
            with self.subTest(name):
                r = scenario_result(name)
                self.assertTrue(r.passed, r.expectation_failures)
                why = ReplaySession.from_source(r).why_lane_isolated(lane)
                self.assertEqual(why[0]["state"], state)
                self.assertTrue(why[0]["reason"])
                self.assertEqual(r.metrics.worst_system_state, "degraded")


class AllocationExclusionTest(unittest.TestCase):
    def test_failed_actuator_receives_no_nominal_allocation(self):
        alloc = ControlAllocator.from_regime(HoverEffectiveness().regime())
        h = np.ones(alloc.B.shape[1])
        h[2] = 0.0
        r = alloc.allocate([240.0, 0.0, 0.0, 0.0], h)
        self.assertEqual(float(r.u[2]), 0.0)          # arızalı eyleyici 0'da sabit
        self.assertTrue(r.feasible)                       # istek sağlam eyleyicilerle karşılanır

    def test_actuator_removal_is_explained_in_replay(self):
        why = ReplaySession.from_source(scenario_result("hover_capability_loss")) \
            .why_actuator_removed("M1U")
        self.assertEqual(len(why), 1)
        self.assertTrue(why[0]["reason"])
        self.assertTrue(why[0]["fdir_history"])


class FlightDataRecorderTest(unittest.TestCase):
    def test_every_event_type_belongs_to_a_recorder_channel(self):
        unmapped = {t.value for t in EventType} - set(CHANNEL_OF)
        self.assertFalse(unmapped, f"kayıt kanalı olmayan olaylar: {sorted(unmapped)}")

    def test_required_channels_exist(self):
        for ch in ("health", "mode", "fdir", "rta", "navigation", "energy", "command", "fcc"):
            self.assertIn(ch, RECORDER_CHANNELS)

    def test_explainability_questions_answered_from_record(self):
        s = ReplaySession.from_source(scenario_result("rta_intervention"))
        self.assertTrue(s.why_rta_intervened()[0]["predicted_violations"])
        nav = ReplaySession.from_source(scenario_result("nav_integrity_loss"))
        self.assertTrue(any(x["type"] == "nav_integrity_lost" for x in nav.why_nav_degraded()))
        ret = ReplaySession.from_source(scenario_result("communication_loss")).why_mode("RETURN")
        self.assertEqual(ret[0]["reason"], "baglanti_kaybi")
        self.assertTrue(s.channel("state"))

    def test_contingency_decisions_record_timestamp_and_inputs(self):
        r = scenario_result("communication_loss")
        c = next(e for e in r.events if e["type"] == EventType.CONTINGENCY.value)
        self.assertEqual(c["data"]["timestamp"], c["time_s"])
        self.assertEqual(c["data"]["recommended_safe_mode"], "RETURN")
        for k in ("vehicle_health_level", "nav_integrity_ok", "rth_energy_ok", "controllable",
                  "link_ok", "rta_latched"):
            self.assertIn(k, c["data"]["inputs"])


if __name__ == "__main__":
    unittest.main()
