"""Paket meta verisi, CI, gizli bilgi ve çevrimdışı çalışma politikası."""

import re
import subprocess
import unittest
from pathlib import Path

import simurg

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def tracked_files() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout.split()
        files = [ROOT / f for f in out]
    except (OSError, subprocess.CalledProcessError):
        files = [p for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts]
    return [p for p in files if p.suffix in {".py", ".md", ".toml", ".yml", ".yaml", ".txt", ".json"}]


class PackagingTest(unittest.TestCase):
    def test_version_single_source_and_semver(self):
        m = re.search(r'^version = "(\d+\.\d+\.\d+)"', PYPROJECT, flags=re.M)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), simurg.__version__)

    def test_runtime_dependencies_minimal(self):
        deps = re.search(r"^dependencies = \[(.*?)\]", PYPROJECT, flags=re.M | re.S).group(1)
        self.assertEqual(re.findall(r'"([^"]+)"', deps), ["numpy>=1.24"])
        self.assertIn('requires-python = ">=3.10"', PYPROJECT)

    def test_ci_runs_unittest_on_supported_pythons(self):
        wf = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
        for v in ("3.10", "3.11", "3.12"):
            self.assertIn(f'"{v}"', wf)
        self.assertIn("python -m unittest discover -s tests -v", wf)
        self.assertIn("pip install -e .", wf)
        self.assertNotIn("secrets.", wf)          # CI gizli bilgi kullanmaz

    def test_gitignore_blocks_local_secrets_and_outputs(self):
        gi = (ROOT / ".gitignore").read_text(encoding="utf-8").split()
        for pat in (".env", ".env.*", "__pycache__/", "dist/", "build/", "*.egg-info/",
                    ".coverage", ".pytest_cache/", "simulation-output/"):
            self.assertIn(pat, gi)


class SecurityPolicyTest(unittest.TestCase):
    PATTERNS = [r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"AKIA[0-9A-Z]{16}", r"ghp_[0-9A-Za-z]{36}",
                r"xox[baprs]-[0-9A-Za-z-]{10,}", r"sk-[0-9A-Za-z]{32,}",
                r"(?i)(api[_-]?key|password|secret|token)\s*[:=]\s*['\"][^'\"\s]{8,}['\"]"]

    def test_no_hardcoded_secrets(self):
        rx = [re.compile(p) for p in self.PATTERNS]
        for p in tracked_files():
            if p.name == "test_packaging.py":
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            for r in rx:
                self.assertIsNone(r.search(text), f"{p.relative_to(ROOT)}: {r.pattern}")

    def test_library_has_no_network_dependencies(self):
        net = re.compile(r"^\s*(import|from)\s+(socket|urllib|http|requests|aiohttp|ftplib|smtplib)\b",
                         re.M)
        for p in (ROOT / "simurg").rglob("*.py"):
            self.assertIsNone(net.search(p.read_text(encoding="utf-8")), p)


if __name__ == "__main__":
    unittest.main()
