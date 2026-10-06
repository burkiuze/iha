import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from simurg.sim.__main__ import main


def run(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        code = main(list(argv))
    return code, buf.getvalue()


class CliTest(unittest.TestCase):
    def test_list(self):
        code, out = run("list")
        self.assertEqual(code, 0)
        self.assertIn("transition_abort", out)

    def test_run_writes_log_and_replay_reads_it(self):
        with tempfile.TemporaryDirectory() as d:
            p = str(Path(d) / "k.json")
            code, out = run("run", "nominal", "--seed", "3", "--duration", "8", "--json", p)
            self.assertEqual(code, 1)          # 8 s'de görev tamamlanamaz -> beklenti başarısız
            log = json.loads(Path(p).read_text(encoding="utf-8"))
            self.assertEqual(log["meta"]["seed"], 3)
            code, out = run("replay", p)
            self.assertEqual(code, 0)
            self.assertIn("sim_started", out)

    def test_library_logger_is_silent(self):
        import logging

        import simurg  # noqa: F401
        handlers = logging.getLogger("simurg").handlers
        self.assertTrue(any(isinstance(h, logging.NullHandler) for h in handlers))

    def test_unknown_scenario_is_domain_error(self):
        code, _ = run("run", "yok")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
