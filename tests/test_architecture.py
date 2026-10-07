"""Mimari kaydının bütünlüğü, kodla izlenebilirliği, yetki değişmezleri ve
mimari-kod denetimi (docs/15 §9 ile aynı fonksiyonlar)."""

import dataclasses
import unittest

from simurg.architecture import ARCHITECTURE
from simurg.architecture import audit
from simurg.architecture.__main__ import architecture_documents, render_document
from simurg.architecture.model import CODE_BACKED, Edge, EdgeKind, Status
from simurg.architecture.render import container_ids, members, spine_edges

try:
    from ._simcache import scenario_result
except ImportError:
    from _simcache import scenario_result

REQUIRED_SUBSYSTEMS = (
    "AIR VEHICLE", "SENSOR SUITE", "AIR DATA", "NAVIGATION", "STATE ESTIMATION", "GUIDANCE",
    "FLIGHT CONTROL", "RUNTIME ASSURANCE", "TRIPLEX FLIGHT COMPUTERS", "FDIR", "VEHICLE HEALTH",
    "CONTROL ALLOCATION", "ACTUATOR SYSTEM", "POWER / ENERGY", "COMMUNICATION", "MISSION COMPUTER",
    "MODE / CONTINGENCY", "SYSTEM SUPERVISION", "TIME / SYNCHRONIZATION", "DATA BUS",
    "FLIGHT DATA RECORDER", "DIGITAL TWIN", "GROUND SEGMENT", "COMMAND VALIDATION",
    "PREFLIGHT SUPERVISOR")


def with_edge(edge):
    return dataclasses.replace(ARCHITECTURE, edges=ARCHITECTURE.edges + (edge,))


class RegistryIntegrityTest(unittest.TestCase):
    def test_architecture_has_at_least_sixty_components(self):
        self.assertGreaterEqual(len(ARCHITECTURE.components), 60)

    def test_master_diagram_has_seventy_to_one_hundred_components(self):
        n = sum(c.master for c in ARCHITECTURE.components)
        self.assertGreaterEqual(n, 70)
        self.assertLessEqual(n, 100)
        for g in ARCHITECTURE.groups:          # her alt sistem ana diyagramda görünür
            self.assertTrue(any(c.master and c.group == g.id for c in ARCHITECTURE.components), g.id)

    def test_component_ids_are_unique(self):
        ids = [c.id for c in ARCHITECTURE.components]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertFalse(set(ids) & set(container_ids(ARCHITECTURE)))

    def test_every_component_belongs_to_a_declared_group_and_subgroup(self):
        groups = {g.id: {sid for sid, _ in g.subgroups} for g in ARCHITECTURE.groups}
        for c in ARCHITECTURE.components:
            self.assertIn(c.group, groups, c.id)
            if c.sub:
                self.assertIn(c.sub, groups[c.group], c.id)

    def test_every_component_documents_responsibility_io_health_and_failure(self):
        for c in ARCHITECTURE.components:
            for field in ("responsibility", "inputs", "outputs", "health", "failure"):
                self.assertTrue(getattr(c, field).strip(), f"{c.id}.{field} boş")

    def test_all_edge_endpoints_exist(self):
        known = set(ARCHITECTURE.by_id()) | set(container_ids(ARCHITECTURE))
        for e in ARCHITECTURE.edges:
            self.assertIn(e.src, known, e)
            self.assertIn(e.dst, known, e)

    def test_authority_gates_are_registered_components(self):
        self.assertEqual(ARCHITECTURE.gates, {"RTA_SELECTOR", "MD_FSM"})
        self.assertTrue(ARCHITECTURE.gates <= set(ARCHITECTURE.by_id()))

    def test_required_subsystems_are_present(self):
        titles = " ".join(container_ids(ARCHITECTURE).values()).upper()
        for word in REQUIRED_SUBSYSTEMS:
            self.assertIn(word, titles)

    def test_sensor_chain_and_lanes_are_decomposed(self):
        ids = set(ARCHITECTURE.by_id())
        for k in ("SEN_IMU_A", "SEN_IMU_B", "SEN_IMU_C", "SEN_GNSS_A", "SEN_GNSS_B", "AIR_BARO_A",
                  "AIR_BARO_B", "SEN_MAG", "SEN_VIO", "SEN_TRN", "SEN_MAGNAV", "SEN_CELESTIAL",
                  "SEN_DRIVER", "SEN_TIMESTAMP", "SEN_SIGNAL_VALID", "SEN_PLAUSIBILITY",
                  "SEN_HEALTH", "SEN_MEAS_BUS", "FCC_COMPARATOR", "FCC_VOTER", "FCC_ISOLATION",
                  "FCC_C_WATCHDOG", "FCC_C_TIMING", "FCC_C_DIVERGENCE"):
            self.assertIn(k, ids)
        self.assertEqual(len(members(ARCHITECTURE, "ACT_M")), 9)     # grup + 8 motor
        self.assertEqual(len(members(ARCHITECTURE, "ACT_E")), 5)     # grup + 4 elevon

    def test_every_status_is_used_honestly(self):
        self.assertEqual({c.status for c in ARCHITECTURE.components}, set(Status))


class CodeTraceabilityTest(unittest.TestCase):
    """IMPLEMENTED/PARTIAL/UNVALIDATED iddiası koda dayanmalı; PLANNED kod iddia etmemeli."""

    def test_implemented_and_partial_components_reference_existing_code(self):
        self.assertEqual(audit.bad_code_refs(ARCHITECTURE), [])
        self.assertTrue(all(c.code for c in ARCHITECTURE.components if c.status in CODE_BACKED))

    def test_planned_components_claim_no_code(self):
        for c in ARCHITECTURE.components:
            if c.status is Status.PLANNED:
                self.assertEqual(c.code, (), c.id)

    def test_critical_code_classes_appear_in_architecture(self):
        self.assertEqual(audit.uncovered_critical_classes(ARCHITECTURE), [])

    def test_not_architectural_allowlist_has_no_stale_entries(self):
        existing = {cls for p in audit.CRITICAL_MODULES for cls in audit.public_classes(p)}
        self.assertEqual(set(audit.NOT_ARCHITECTURAL) - existing, set())


class AuthorityBoundaryTest(unittest.TestCase):
    """YZ / görev katmanı yalnızca öneri üretir; eyleyicilere yetki geçidi dışında yol yoktur."""

    def test_no_authority_path_bypasses_gates(self):
        self.assertTrue(audit.proposal_nodes(ARCHITECTURE))
        self.assertEqual(audit.authority_leaks(ARCHITECTURE), set())

    def test_bypass_detection_catches_direct_and_indirect_paths(self):
        direct = with_edge(Edge("MC_AI", "AL_ALLOCATOR", "x", EdgeKind.COMMAND))
        self.assertIn("AL_ALLOCATOR", audit.authority_leaks(direct))
        self.assertTrue(audit.direct_proposal_edges(direct))
        indirect = with_edge(Edge("MC_HEALTH", "ACT_HEALTH_GATE", "x", EdgeKind.SUPERVISORY))
        self.assertIn("ACT_HEALTH_GATE", audit.authority_leaks(indirect))

    def test_proposal_layer_has_no_direct_edges_to_actuation(self):
        self.assertEqual(audit.direct_proposal_edges(ARCHITECTURE), [])

    def test_mission_computer_components_are_all_proposal_only(self):
        for c in ARCHITECTURE.components:
            if c.group == "MC":
                self.assertTrue(c.proposal_only, c.id)

    def test_gate_reaches_actuators(self):
        self.assertTrue(audit.gate_reaches_actuators(ARCHITECTURE))

    def test_proposals_pass_command_validator_before_rta(self):
        path = audit.reachable(ARCHITECTURE, audit.proposal_nodes(ARCHITECTURE),
                               (EdgeKind.COMMAND,), stop_at={"CV_VALIDATOR"})
        self.assertNotIn("RTA_SELECTOR", path)
        self.assertIn("CV_VALIDATOR", path)


class AuditTest(unittest.TestCase):
    def test_every_audit_check_passes(self):
        failed = [(r.check, r.detail) for r in audit.run(ARCHITECTURE) if not r.passed]
        self.assertEqual(failed, [])

    def test_every_single_point_of_failure_candidate_is_documented(self):
        self.assertTrue(audit.spof_candidates(ARCHITECTURE))
        self.assertEqual(audit.unmitigated_spofs(ARCHITECTURE), [])

    def test_safety_invariants_and_failsafe_rules_map_to_existing_tests(self):
        self.assertEqual(audit.missing_failsafe_tests(audit.SAFETY_INVARIANTS), [])
        self.assertEqual(audit.missing_failsafe_tests(), [])

    def test_failure_chains_are_observed_in_their_scenarios(self):
        self.assertEqual(audit.failure_chain_problems(ARCHITECTURE), [])
        self.assertGreaterEqual(len(ARCHITECTURE.failure_chains), 9)
        for ch in ARCHITECTURE.failure_chains:
            with self.subTest(ch.id):
                r = scenario_result(ch.scenario)
                types = {e["type"] for e in r.events}
                self.assertTrue(set(ch.events) <= types, set(ch.events) - types)
                self.assertTrue(r.passed, r.expectation_failures)


class DocumentSyncTest(unittest.TestCase):
    def test_generated_blocks_in_architecture_docs_are_in_sync(self):
        docs = architecture_documents()
        self.assertGreaterEqual(len(docs), 11)
        for path in docs:
            with self.subTest(path.name):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(render_document(text), text,
                                 "python -m simurg.architecture --update-all")

    def test_master_diagram_main_flow_is_connected(self):
        drawn = {(s, d) for s, d, _ in spine_edges(ARCHITECTURE)}
        for pair in (("SEN", "NAV"), ("NAV", "EST"), ("EST", "GUID"), ("GUID", "MC"),
                     ("MC", "CV"), ("CV", "RTA"), ("RTA", "CTRL"), ("CTRL", "ALLOC"),
                     ("ALLOC", "FCC"), ("FCC", "ACT")):
            self.assertIn(pair, drawn)


if __name__ == "__main__":
    unittest.main()
