import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from main import handle
from scheduler.graph import DependencyGraph
from scheduler.storage import load_data, parse_date, parse_int

ROOT = Path(__file__).resolve().parent.parent


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.g = DependencyGraph()

    def test_add_depend_schedule(self):
        handle(self.g, "add build 3 2026-11-05")
        handle(self.g, "add test 4 2026-11-01")
        handle(self.g, "depend test build")
        out = handle(self.g, "schedule")
        self.assertLess(out.index("build"), out.index("test"))

    def test_bad_inputs_return_messages_not_crashes(self):
        for line in ("add x 9 2026-11-01", "add x 3 not-a-date",
                     "add x three 2026-11-01", "add x", "depend a b",
                     "nonsense"):
            out = handle(self.g, line)
            self.assertIsInstance(out, str)
            self.assertTrue(out)

    def test_cycle_reported(self):
        for t in ("x", "y"):
            handle(self.g, f"add {t} 3 2026-11-01")
        handle(self.g, "depend x y")
        handle(self.g, "depend y x")
        self.assertIn("Circular dependency", handle(self.g, "schedule"))

    def test_critical_command(self):
        handle(self.g, "add a 3 2026-11-01 2")
        handle(self.g, "add b 3 2026-11-01 4")
        handle(self.g, "depend b a")
        self.assertEqual(handle(self.g, "critical"),
                         "Critical path (6 days): a -> b")

    def test_bad_duration_returns_message(self):
        self.assertIn("Duration", handle(self.g, "add a 3 2026-11-01 0"))
        self.assertIn("Error", handle(self.g, "add a 3 2026-11-01 many"))

    def test_quit_returns_none(self):
        self.assertIsNone(handle(self.g, "quit"))


class TestEditCommand(unittest.TestCase):
    def setUp(self):
        self.g = DependencyGraph()
        for line in ("add build 3 2026-11-05 2", "add test 4 2026-11-06", "depend test build"):
            handle(self.g, line)

    def test_each_field(self):
        self.assertIn("Changed", handle(self.g, "edit build days 5"))
        self.assertIn("Changed", handle(self.g, "edit build priority 1"))
        self.assertIn("Changed", handle(self.g, "edit build deadline 2026-12-01"))
        t = self.g.tasks["build"]
        self.assertEqual((t.duration, t.priority, str(t.deadline)), (5, 1, "2026-12-01"))

    def test_field_names_are_not_case_sensitive(self):
        handle(self.g, "edit build DAYS 7")
        self.assertEqual(self.g.tasks["build"].duration, 7)

    def test_rename_keeps_links(self):
        handle(self.g, "edit build name compile")
        self.assertEqual(self.g.prerequisites["test"], {"compile"})
        self.assertNotIn("build", self.g.tasks)

    def test_errors_are_messages_and_change_nothing(self):
        before = dict(self.g.tasks)
        for line in ("edit build priority 9", "edit build priority x", "edit build deadline 2026-02-30",
                     "edit build deadline 5/11/2026", "edit build days 0", "edit build days many",
                     "edit build name test", "edit nope days 2", "edit build",
                     "edit build colour red", "edit build days 1 extra", "edit"):
            out = handle(self.g, line)
            self.assertIsInstance(out, str, line)
            self.assertTrue(out.startswith(("Error", "Usage")), (line, out))
        self.assertEqual(self.g.tasks, before)

    def test_schedule_reflects_the_edit(self):
        handle(self.g, "add other 3 2026-11-07")
        handle(self.g, "edit other deadline 2026-11-01")
        self.assertTrue(handle(self.g, "schedule").splitlines()[0].startswith("1. other"))


class TestParsing(unittest.TestCase):
    def test_parse_int(self):
        self.assertEqual(parse_int("x", "7"), 7)
        self.assertEqual(parse_int("x", 7), 7)
        for bad in ("3.5", "abc", "", "3_0", True, 3.0, None):
            with self.assertRaises(ValueError):
                parse_int("x", bad)

    def test_parse_date_is_strict(self):
        self.assertEqual(str(parse_date("2026-11-05")), "2026-11-05")
        for bad in ("20261105", "05-11-2026", "2026-13-01", "2026-02-30", "2026-1-5", 20261105):
            with self.assertRaises(ValueError):
                parse_date(bad)

    def test_friendly_messages_not_python_internals(self):
        g = DependencyGraph()
        for line in ("add a three 2026-11-01", "add a 3 nope", "add a 3 2026-11-01 many"):
            out = handle(g, line)
            self.assertNotIn("literal for int", out)
            self.assertNotIn("isoformat", out)


class TestLoading(unittest.TestCase):
    def good(self, **extra):
        data = {"tasks": [{"id": "a", "priority": 3, "deadline": "2026-11-01"},
                          {"id": "b", "priority": 2, "deadline": "2026-11-02", "duration": 4}],
                "dependencies": [["b", "a"]]}
        data.update(extra)
        return data

    def test_valid_data_loads(self):
        g = DependencyGraph()
        load_data(g, self.good())
        self.assertEqual(g.tasks["b"].duration, 4)
        self.assertEqual(g.in_degree("b"), 1)

    def test_numeric_ids_are_treated_as_text(self):
        g = DependencyGraph()
        load_data(g, {"tasks": [{"id": 1, "priority": 3, "deadline": "2026-11-01"},
                                {"id": 2, "priority": 3, "deadline": "2026-11-01"}],
                      "dependencies": [[2, 1]]})
        self.assertEqual(g.in_degree("2"), 1)

    def test_bad_structures_raise_value_error(self):
        bad_inputs = [
            [], {}, {"tasks": "x"}, {"tasks": ["a"]},
            {"tasks": [{"id": "a", "priority": 3}]},
            {"tasks": [{"id": "a", "priority": "x", "deadline": "2026-11-01"}]},
            {"tasks": [{"id": "a", "priority": 3, "deadline": "2026-11-01", "duration": 0}]},
            {"tasks": [{"id": "a", "priority": 3, "deadline": "2026-11-01"}] * 2},
            self.good(dependencies=[["a"]]),
            self.good(dependencies=[["a", "ghost"]]),
            self.good(dependencies="nope"),
        ]
        for data in bad_inputs:
            with self.assertRaises(ValueError, msg=repr(data)):
                load_data(DependencyGraph(), data)


class TestCommandLine(unittest.TestCase):
    """Runs main.py as a real process, from a different working directory."""

    def run_main(self, args, stdin):
        return subprocess.run([sys.executable, str(ROOT / "main.py"), *args],
                              input=stdin, capture_output=True, text=True,
                              cwd=tempfile.gettempdir(), timeout=30)

    def test_demo_flag_end_to_end(self):
        r = self.run_main(["--demo", "--commands"], "schedule\ncritical\nquit\n")
        self.assertEqual(r.returncode, 0)
        self.assertIn("5. deploy", r.stdout)
        self.assertIn("Critical path (6 days): build -> test -> deploy", r.stdout)

    def test_missing_file_exits_with_message(self):
        r = self.run_main(["--file", "does_not_exist.json"], "")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Could not load tasks", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_malformed_file_exits_with_message(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("{bad json")
        r = self.run_main(["--file", f.name], "")
        self.assertEqual(r.returncode, 1)
        self.assertIn("not valid JSON", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_cycle_file_reports_cycle(self):
        r = self.run_main(["--file", str(ROOT / "examples" / "cycle.json"), "--commands"], "schedule\nquit\n")
        self.assertIn("Circular dependency", r.stdout)
        self.assertIn("blocked by the cycle: d", r.stdout)

    def test_end_of_input_exits_cleanly(self):
        r = self.run_main([], "")
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)


class TestDemoCommand(unittest.TestCase):
    def test_demo_loads_into_empty_graph_only(self):
        g = DependencyGraph()
        self.assertIn("Demo loaded", handle(g, "demo"))
        self.assertIn("empty", handle(g, "demo"))
        self.assertEqual(len(g.tasks), 5)           # second call changed nothing


if __name__ == "__main__":
    unittest.main()
