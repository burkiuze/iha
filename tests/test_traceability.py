"""Gereksinim -> uygulama -> test izlenebilirliğinin otomatik denetimi."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQS = (ROOT / "docs" / "01-gereksinimler.md").read_text(encoding="utf-8")
TEST_REF = re.compile(r"`(test_[a-z0-9_]+)\.([A-Za-z0-9_*]+)`")


class TraceabilityTest(unittest.TestCase):
    def test_every_test_reference_exists(self):
        refs = TEST_REF.findall(REQS)
        self.assertGreater(len(refs), 40)
        for module, name in refs:
            path = ROOT / "tests" / f"{module}.py"
            self.assertTrue(path.exists(), f"{module}.py yok")
            if name != "*":
                self.assertIn(f"def {name}(", path.read_text(encoding="utf-8"),
                              f"{module}.{name} bulunamadı")

    def test_sim_requirements_have_implementation_and_tests(self):
        rows = [ln for ln in REQS.splitlines() if ln.startswith("| SYS-SIM-")]
        self.assertGreaterEqual(len(rows), 25)
        ids = [r.split("|")[1].strip() for r in rows]
        self.assertEqual(len(ids), len(set(ids)), "yinelenen kimlik")
        for r in rows:
            cols = [c.strip() for c in r.strip().strip("|").split("|")]
            impl = re.findall(r"`([\w./-]+\.(?:py|toml|yml))`", cols[2])
            self.assertTrue(impl, f"{cols[0]}: uygulama yok")
            for p in impl:
                self.assertTrue((ROOT / p).exists(), f"{cols[0]}: {p} yok")
            self.assertTrue(TEST_REF.search(cols[3]), f"{cols[0]}: test yok")

    def test_requirement_ids_unique(self):
        ids = re.findall(r"^\| (SYS-[A-Z]+-\d{3}) \|", REQS, flags=re.M)
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
