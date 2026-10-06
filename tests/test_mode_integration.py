import re
import unittest
from pathlib import Path

import numpy as np

from simurg.core.events import EventType
from simurg.modes.flight_modes import (CONTINGENCY_RULES, TRANSITIONS, Context,
                                       ContingencyManager, FlightModeMachine, Mode)

try:                                   # python -m unittest tests.test_x
    from ._simcache import scenario_result
except ImportError:                    # python -m unittest discover -s tests
    from _simcache import scenario_result

DOCS = Path(__file__).resolve().parent.parent / "docs"


def legacy_evaluate(m: Mode, ctx: Context):
    """v0.1 ContingencyManager mantığının birebir kopyası (eşdeğerlik referansı)."""
    if m in (Mode.PARACHUTE, Mode.DISARMED, Mode.PREFLIGHT, Mode.ARMED):
        return None
    if not ctx.controllable:
        return Mode.PARACHUTE, "kontrol_kaybi"
    if m is Mode.EMERGENCY_LAND:
        return None
    if not ctx.land_energy_ok or not ctx.hover_feasible:
        return Mode.EMERGENCY_LAND, "enerji_veya_hover_yok"
    if not ctx.rth_energy_ok and m not in (Mode.TRANSITION_VTOL, Mode.VTOL_LAND):
        return Mode.EMERGENCY_LAND, "eve_donus_enerjisi_yok"
    if not ctx.nav_integrity_ok and m in (Mode.CRUISE, Mode.MISSION, Mode.RETURN):
        return Mode.LOITER_HOLD, "nav_butunluk_kaybi"
    if ctx.link_lost_s > 30 and m in (Mode.CRUISE, Mode.MISSION, Mode.LOITER_HOLD):
        if m is Mode.LOITER_HOLD and not ctx.nav_integrity_ok:
            return None
        return Mode.RETURN, "baglanti_kaybi"
    return None


class DetailedTransitionTest(unittest.TestCase):
    def test_invalid_transition_diagnostics(self):
        t = [0.0]
        seen = []
        fsm = FlightModeMachine(clock=lambda: t[0], listener=seen.append)
        rec = fsm.request_detailed(Mode.MISSION, Context(preflight_ok=True))
        self.assertFalse(rec.accepted)
        self.assertIsNone(rec.guard_result)
        self.assertTrue(rec.diagnostic.startswith("tablo_disi_gecis"))
        t[0] = 3.0
        rec = fsm.request_detailed(Mode.ARMED, Context(preflight_ok=False), "test")
        self.assertEqual((rec.accepted, rec.guard_result), (False, False))
        self.assertEqual(rec.diagnostic, "koruma_kosulu_saglanmadi")
        rec = fsm.request_detailed(Mode.ARMED, Context(preflight_ok=True), "test")
        self.assertTrue(rec.accepted)
        self.assertEqual((rec.source, rec.target, rec.timestamp), (Mode.PREFLIGHT, Mode.ARMED, 3.0))
        self.assertEqual(len(seen), 3)
        self.assertEqual(fsm.history, [(Mode.PREFLIGHT, Mode.ARMED, "test")])

    def test_request_keeps_bool_api_and_table_is_single_source(self):
        fsm = FlightModeMachine()
        self.assertFalse(fsm.request(Mode.CRUISE, Context()))
        for (src, tgt) in TRANSITIONS:
            self.assertIn(tgt, FlightModeMachine.allowed_targets(src))


class ContingencyTableTest(unittest.TestCase):
    def test_rule_table_equivalent_to_legacy_logic(self):
        rng = np.random.default_rng(11)
        cm = ContingencyManager()
        for _ in range(3000):
            mode = list(Mode)[int(rng.integers(len(Mode)))]
            ctx = Context(preflight_ok=True, link_lost_s=float(rng.choice([0.0, 10.0, 31.0])),
                          rth_energy_ok=bool(rng.random() > .3), land_energy_ok=bool(rng.random() > .2),
                          nav_integrity_ok=bool(rng.random() > .3), hover_feasible=bool(rng.random() > .2),
                          controllable=bool(rng.random() > .2), landed=False, airspeed_mps=3.0)
            fsm = FlightModeMachine()
            fsm.mode = mode
            d = cm.evaluate_detailed(fsm, ctx)
            ref = legacy_evaluate(mode, ctx)
            got = None if d is None or d.requested_mode is None else (d.requested_mode, d.trigger)
            self.assertEqual(got, ref, (mode, ctx))

    def test_decision_object(self):
        fsm = FlightModeMachine()
        fsm.mode = Mode.MISSION
        d = ContingencyManager().evaluate_detailed(fsm, Context(link_lost_s=40.0, landed=False))
        self.assertEqual((d.requested_mode, d.trigger, d.priority, d.accepted),
                         (Mode.RETURN, "baglanti_kaybi", 6, True))
        self.assertEqual(fsm.mode, Mode.RETURN)

    def test_docs_table_matches_code(self):
        text = (DOCS / "08-otonomi-ve-guvenlik.md").read_text(encoding="utf-8")
        section = text.split("## 3. Acil durum yöneticisi", 1)[1].split("\n## ", 1)[0]
        rows = [ln for ln in section.splitlines() if re.match(r"\|\s*\d+\s*\|", ln)]
        doc = [(int(re.match(r"\|\s*(\d+)", r).group(1)), re.search(r"`([a-z_]+)`", r).group(1))
               for r in rows]
        code = [(r.priority, r.trigger) for r in CONTINGENCY_RULES]
        self.assertEqual(doc, code)


class ModesInSimulationTest(unittest.TestCase):
    def test_link_loss_return_after_30_s(self):
        r = scenario_result("communication_loss")
        self.assertTrue(r.passed, r.expectation_failures)
        lost = next(e for e in r.events if e["type"] == EventType.LINK_LOST.value)
        c = next(e for e in r.events if e["type"] == EventType.CONTINGENCY.value)
        self.assertEqual((c["data"]["trigger"], c["data"]["requested_mode"]), ("baglanti_kaybi", "RETURN"))
        self.assertGreaterEqual(c["time_s"] - lost["time_s"], 30.0)
        self.assertLess(c["time_s"] - lost["time_s"], 30.1)

    def test_nav_integrity_loss_loiters_then_resumes(self):
        r = scenario_result("nav_integrity_loss")
        self.assertTrue(r.passed, r.expectation_failures)
        seq = [(e["data"]["source"], e["data"]["target"]) for e in r.events
               if e["type"] == EventType.MODE_TRANSITION.value]
        i = seq.index(("MISSION", "LOITER_HOLD"))
        self.assertEqual(seq[i + 1], ("LOITER_HOLD", "CRUISE"))
        self.assertIn(("CRUISE", "MISSION"), seq[i + 1:])

    def test_hover_loss_glides_and_control_loss_deploys_parachute(self):
        r = scenario_result("hover_capability_loss")
        self.assertTrue(r.passed, r.expectation_failures)
        c = [e["data"] for e in r.events if e["type"] == EventType.CONTINGENCY.value]
        self.assertEqual(c[0]["trigger"], "enerji_veya_hover_yok")
        td = next(e for e in r.events if e["type"] == EventType.TOUCHDOWN.value)
        self.assertEqual(td["data"]["kind"], "emergency_glide")

        r = scenario_result("loss_of_control")
        self.assertTrue(r.passed, r.expectation_failures)
        triggers = [e["data"]["trigger"] for e in r.events if e["type"] == EventType.CONTINGENCY.value]
        self.assertEqual(triggers[-1], "kontrol_kaybi")
        td = next(e for e in r.events if e["type"] == EventType.TOUCHDOWN.value)
        self.assertEqual(td["data"]["kind"], "parachute")
        self.assertFalse(r.metrics.impact)

    def test_rejected_transitions_never_change_mode(self):
        r = scenario_result("nominal")
        for e in r.events:
            if e["type"] == EventType.MODE_REJECTED.value:
                self.assertFalse(e["data"]["accepted"])


if __name__ == "__main__":
    unittest.main()
