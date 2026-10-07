"""Önemli kararlar kayıt/tekrar oynatmadan açıklanabilir mi? (docs/14 §7)"""

import unittest

from simurg.core.events import EventType
from simurg.sim import ReplaySession
from simurg.sim.scenarios import SCENARIOS

try:
    from ._simcache import scenario_result
except ImportError:
    from _simcache import scenario_result

# Bu olay türleri her zaman gerekçe taşımalı; bileşen düzeyindekiler bileşen de taşımalı.
NEEDS_REASON = {EventType.MODE_TRANSITION, EventType.CONTINGENCY, EventType.RTA_INTERVENTION,
                EventType.RTA_RECOVERY, EventType.RTA_LATCHED, EventType.FDIR_WARNING,
                EventType.FDIR_FAILURE, EventType.NAV_SOURCE_REJECTED,
                EventType.NAV_SOURCE_UNAVAILABLE, EventType.NAV_INTEGRITY_LOST,
                EventType.NAV_INTEGRITY_RESTORED, EventType.LINK_LOST, EventType.LINK_RESTORED,
                EventType.ENERGY_WARNING, EventType.TRANSITION_ABORTED, EventType.MISSION_ABORT,
                EventType.MISSION_COMPLETE, EventType.TOUCHDOWN, EventType.IMPACT,
                EventType.SENSOR_DEGRADED, EventType.SENSOR_RESTORED,
                EventType.PREFLIGHT_PASSED, EventType.PREFLIGHT_FAILED,
                EventType.COMMAND_REJECTED, EventType.COMMAND_ACCEPTED,
                EventType.VEHICLE_HEALTH_CHANGED, EventType.SYSTEM_STATE_CHANGED}
NEEDS_COMPONENT = {EventType.FDIR_WARNING, EventType.FDIR_FAILURE, EventType.NAV_SOURCE_REJECTED,
                   EventType.NAV_SOURCE_UNAVAILABLE, EventType.LINK_LOST, EventType.ENERGY_WARNING,
                   EventType.RTA_INTERVENTION, EventType.CONTINGENCY, EventType.SENSOR_DEGRADED}


def replay(name):
    return ReplaySession.from_source(scenario_result(name))


class StructuredEventTest(unittest.TestCase):
    def test_safety_events_carry_reason_and_component(self):
        for name in SCENARIOS:
            for e in scenario_result(name).events:
                t = EventType(e["type"])
                if t in NEEDS_REASON:
                    self.assertTrue(e["data"].get("reason"), (name, e))
                if t in NEEDS_COMPONENT:
                    self.assertTrue(e["data"].get("component"), (name, e))


class ExplainabilityQuestionsTest(unittest.TestCase):
    def test_why_did_mode_become_return(self):
        why = replay("communication_loss").why_mode("RETURN")
        self.assertEqual(why[0]["reason"], "baglanti_kaybi")
        self.assertEqual(why[0]["contingency_rule"]["trigger"], "baglanti_kaybi")
        self.assertEqual(why[0]["contingency_rule"]["priority"], 6)
        nominal = replay("nominal").why_mode("RETURN")
        self.assertEqual(nominal[0]["reason"], "ara_noktalar_tamam")
        self.assertIsNone(nominal[0]["contingency_rule"])

    def test_why_rta_intervened_and_which_constraint(self):
        h = replay("rta_intervention").rta_history()[0]
        self.assertEqual(h["selected_source"], "safety")
        self.assertIn("asiri_yatis", h["predicted_violations"])

    def test_why_nav_source_was_rejected_and_which_sources_were_used(self):
        s = replay("combined_degraded")
        rej = s.nav_rejections()[0]
        self.assertEqual(rej["source"], "GNSS")
        self.assertEqual(rej["reason"], "tutarlilik_testi_dislama")
        self.assertGreater(rej["test_statistic"], rej["threshold"])          # dışlamayı tetikleyen
        self.assertLessEqual(rej["test_statistic_after"], rej["threshold_after"])  # sonra tutarlı
        self.assertNotIn("GNSS", rej["sources_used"])
        self.assertNotIn("GNSS", s.nav_sources_at(rej["time_s"] + 5.0))
        self.assertIn("GNSS", s.nav_sources_at(30.0))

    def test_why_motor_degraded_or_failed(self):
        deg = replay("single_actuator_degradation").events_of(EventType.FDIR_WARNING)[0]["data"]
        self.assertEqual((deg["component"], deg["reason"]), ("M2U", "cusum_devir_artigi"))
        self.assertGreater(deg["monitor"]["cusum"], deg["monitor"]["cusum_threshold"])
        fail = replay("hover_capability_loss").events_of(EventType.FDIR_FAILURE)[0]["data"]
        self.assertEqual(fail["reason"], "devir_yok")
        self.assertEqual(fail["health_score"], 0.0)

    def test_which_fault_was_injected_when(self):
        ft = replay("combined_degraded").fault_timeline()
        self.assertEqual([(round(t), typ, fid) for t, typ, fid in ft],
                         [(8, "fault_injected", "F1"), (60, "fault_injected", "F2"),
                          (80, "fault_injected", "F3"), (100, "fault_cleared", "F3")])

    def test_why_mission_was_not_completed(self):
        self.assertEqual(replay("nominal").explain()["mission_outcome"], "tamamlandi")
        self.assertEqual(replay("energy_reserve_warning").explain()["mission_outcome"],
                         "iptal:enerji_uyarisi")
        self.assertTrue(replay("transition_abort").explain()["mission_outcome"]
                        .startswith("iptal:gecis_iptal:"))
        self.assertEqual(replay("communication_loss").explain()["mission_outcome"],
                         "ara_noktalar_tamamlanmadan_indi")

    def test_why_energy_reserve_warning(self):
        w = replay("energy_reserve_warning").explain()["energy"][0]
        self.assertLess(w["usable_wh"], w["warning_factor"] * w["required_wh"])

    def test_why_transition_aborted(self):
        tr = replay("transition_abort").explain()["transitions"]
        aborted = [x for x in tr if x["type"] == "transition_aborted"]
        self.assertEqual(aborted[0]["reason"], "eyleyici_doymasi")


if __name__ == "__main__":
    unittest.main()
