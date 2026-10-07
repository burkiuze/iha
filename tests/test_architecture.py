"""Mimari kaydının bütünlüğü, kodla izlenebilirliği ve yetki değişmezleri."""

import re
import unittest
from collections import deque
from pathlib import Path

from simurg.architecture import ARCHITECTURE
from simurg.architecture.__main__ import render_document
from simurg.architecture.model import EdgeKind, Status
from simurg.architecture.render import container_ids, members, spine_edges

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "15-sistem-mimarisi.md"

# Eyleyici yetkisi taşıyan bölge: kontrol dağıtımı, eyleyiciler, uçuş
# bilgisayarı şeritleri ve GNC kontrol alt grubu.
ACTUATION_GROUPS = ("ALLOC", "ACT", "LANEA", "LANEB", "LANEC", "LANEM")
ACTUATION_SUBGROUPS = ("GNC_C",)
AUTHORITY_KINDS = (EdgeKind.COMMAND, EdgeKind.SUPERVISORY)


def _expand(a, node):
    """Bileşen kimliği -> {kimlik}; grup/alt grup kimliği -> üyeleri."""
    return {node} if node in a.by_id() else set(members(a, node))


def _successors(a, kinds):
    succ = {c.id: set() for c in a.components}
    for e in a.edges:
        if e.kind not in kinds:
            continue
        for s in _expand(a, e.src):
            succ[s] |= _expand(a, e.dst)
    return succ


def _actuation_nodes(a):
    out = set()
    for gid in ACTUATION_GROUPS + ACTUATION_SUBGROUPS:
        out |= set(members(a, gid))
    return out


def _reachable(a, starts, kinds, stop_at=frozenset()):
    succ = _successors(a, kinds)
    seen, todo = set(starts), deque(starts)
    while todo:
        n = todo.popleft()
        if n in stop_at:
            continue
        for m in succ[n] - seen:
            seen.add(m)
            todo.append(m)
    return seen


class RegistryIntegrityTest(unittest.TestCase):
    def test_architecture_has_at_least_sixty_components(self):
        self.assertGreaterEqual(len(ARCHITECTURE.components), 60)

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

    def test_all_edge_endpoints_exist(self):
        known = set(ARCHITECTURE.by_id()) | set(container_ids(ARCHITECTURE))
        for e in ARCHITECTURE.edges:
            self.assertIn(e.src, known, e)
            self.assertIn(e.dst, known, e)

    def test_authority_gates_are_registered_components(self):
        self.assertTrue(ARCHITECTURE.gates)
        self.assertTrue(ARCHITECTURE.gates <= set(ARCHITECTURE.by_id()))

    def test_required_subsystems_are_present(self):
        titles = " ".join(container_ids(ARCHITECTURE).values()).upper()
        for word in ("SENSOR", "MISSION", "NAVIGATION", "GNC", "RTA", "LANE A", "LANE B",
                     "MONITOR", "ALLOCATION", "ACTUATOR", "FDIR", "ENERGY", "COMMUNICATION",
                     "CONTINGENCY", "PREFLIGHT", "SYSTEM SUPERVISOR", "DATA BUS", "TIME",
                     "CONFIGURATION", "FLIGHT DATA RECORDER", "DIGITAL TWIN", "GROUND"):
            self.assertIn(word, titles)


class CodeTraceabilityTest(unittest.TestCase):
    """IMPLEMENTED/PARTIAL iddiası koda dayanmalı; PLANNED kod iddia etmemeli."""

    def test_implemented_and_partial_components_reference_existing_code(self):
        for c in ARCHITECTURE.components:
            if c.status is Status.PLANNED:
                continue
            self.assertTrue(c.code, f"{c.id}: {c.status.value} ama kod referansı yok")
            for ref in c.code:
                path, _, symbol = ref.partition("::")
                f = ROOT / path
                self.assertTrue(f.is_file(), f"{c.id}: {path} yok")
                if symbol:
                    name = re.escape(symbol.split(".")[-1])
                    rx = rf"^\s*(class|def)\s+{name}\b|^\s*{name}\s*(:[^=]*)?="
                    self.assertRegex(f.read_text(encoding="utf-8"), re.compile(rx, re.M),
                                     f"{c.id}: {ref} sembolü bulunamadı")

    def test_planned_components_claim_no_code(self):
        for c in ARCHITECTURE.components:
            if c.status is Status.PLANNED:
                self.assertEqual(c.code, (), c.id)

    def test_status_mix_is_honest(self):
        statuses = {c.status for c in ARCHITECTURE.components}
        self.assertEqual(statuses, set(Status))


class AuthorityBoundaryTest(unittest.TestCase):
    """YZ / görev katmanı yalnızca öneri üretir; eyleyicilere yetki geçidi dışında yol yoktur."""

    def test_no_authority_path_bypasses_gates(self):
        a = ARCHITECTURE
        starts = {c.id for c in a.components if c.proposal_only}
        self.assertTrue(starts)
        reached = _reachable(a, starts, AUTHORITY_KINDS, stop_at=a.gates)
        leaked = (reached - a.gates) & _actuation_nodes(a)
        self.assertFalse(leaked, f"öneri katmanı geçitsiz ulaşıyor: {sorted(leaked)}")

    def test_proposal_layer_has_no_direct_edges_to_actuation(self):
        a = ARCHITECTURE
        proposal = {c.id for c in a.components if c.proposal_only}
        act = _actuation_nodes(a) | set(ACTUATION_GROUPS) | set(ACTUATION_SUBGROUPS)
        for e in a.edges:
            if e.src in proposal:
                self.assertNotIn(e.dst, act, e)

    def test_mission_computer_components_are_all_proposal_only(self):
        for c in ARCHITECTURE.components:
            if c.group == "MC":
                self.assertTrue(c.proposal_only, c.id)

    def test_gate_reaches_actuators(self):
        a = ARCHITECTURE
        reached = _reachable(a, {"RTA_SELECTOR"}, (EdgeKind.COMMAND,))
        self.assertTrue(reached & set(members(a, "ACT")))

    def test_proposal_reaches_actuators_only_through_rta_selector(self):
        a = ARCHITECTURE
        starts = {c.id for c in a.components if c.proposal_only}
        blocked = _reachable(a, starts, (EdgeKind.COMMAND,), stop_at={"RTA_SELECTOR", "MD_FSM"})
        self.assertFalse(blocked & set(members(a, "ACT")))
        self.assertIn("RTA_SELECTOR", blocked)


class DocumentSyncTest(unittest.TestCase):
    def test_generated_blocks_in_architecture_doc_are_in_sync(self):
        text = DOC.read_text(encoding="utf-8")
        self.assertEqual(render_document(text), text,
                         "python -m simurg.architecture --update docs/15-sistem-mimarisi.md")

    def test_full_diagram_main_flow_is_connected(self):
        drawn = {(s, d) for s, d, _ in spine_edges(ARCHITECTURE)}
        for pair in (("SEN", "NAV"), ("NAV", "GNC"), ("GNC", "RTA"), ("RTA", "GNC"),
                     ("GNC", "ALLOC"), ("ALLOC", "ACT"), ("ACT", "SEN")):
            self.assertIn(pair, drawn)


if __name__ == "__main__":
    unittest.main()
