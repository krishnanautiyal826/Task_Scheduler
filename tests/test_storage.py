import json
import os
import stat
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scheduler.graph import DependencyGraph
from scheduler.scheduler import schedule
from scheduler.storage import graph_to_data, load_data, load_file, parse_int, save_file
from scheduler.task import Task


def sample():
    g = DependencyGraph()
    g.add_task(Task("Write report", 4, date(2026, 11, 3), 2))
    g.add_task(Task("Make slides", 2, date(2026, 11, 1)))
    g.add_task(Task("Send, final", 5, date(2026, 11, 9), 3))
    g.add_dependency("Write report", "Make slides")
    g.add_dependency("Send, final", "Write report")
    return g


class TestSaveLoad(unittest.TestCase):
    def test_round_trip_keeps_everything(self):
        g = sample()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "t.json"
            save_file(g, path)
            h = DependencyGraph()
            load_file(h, path)
        self.assertEqual(graph_to_data(g), graph_to_data(h))
        self.assertEqual([t.id for t in schedule(g)], [t.id for t in schedule(h)])
        self.assertEqual(h.tasks["Send, final"].duration, 3)

    def test_task_order_preserved(self):
        g = sample()
        with tempfile.TemporaryDirectory() as d:
            save_file(g, Path(d) / "t.json")
            h = DependencyGraph()
            load_file(h, Path(d) / "t.json")
        self.assertEqual(list(h.tasks), list(g.tasks))

    def test_empty_graph_round_trips(self):
        with tempfile.TemporaryDirectory() as d:
            save_file(DependencyGraph(), Path(d) / "t.json")
            h = DependencyGraph()
            load_file(h, Path(d) / "t.json")
        self.assertEqual(h.tasks, {})

    def test_overwrite_leaves_no_temp_files(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "t.json"
            save_file(sample(), path)
            save_file(DependencyGraph(), path)
            self.assertEqual(os.listdir(d), ["t.json"])
            self.assertEqual(json.loads(path.read_text())["tasks"], [])

    def test_failed_save_keeps_old_file_and_cleans_up(self):
        g = sample()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "t.json"
            save_file(g, path)
            before = path.read_text()
            g.tasks["bad"] = object()          # makes serialising fail midway
            with self.assertRaises(Exception):
                save_file(g, path)
            self.assertEqual(path.read_text(), before)
            self.assertEqual(os.listdir(d), ["t.json"])

    def test_unwritable_folder_raises_oserror(self):
        with self.assertRaises(OSError):
            save_file(sample(), "/nonexistent-folder-xyz/t.json")


class TestRobustness(unittest.TestCase):
    """Regression tests for bugs found while auditing."""

    def test_deeply_nested_json_is_a_value_error_not_a_crash(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "deep.json"
            path.write_text("[" * 200000 + "]" * 200000)
            with self.assertRaises(ValueError) as ctx:
                load_file(DependencyGraph(), path)
            self.assertIn("nested too deeply", str(ctx.exception))

    def test_parse_int_accepts_only_short_ascii_numbers(self):
        for good in ("0", "7", "-3", "999999999"):
            parse_int("x", good)
        for bad in ("٣", "²", "１", "9" * 10, "9" * 5000, "3.5", " 3", ""):
            with self.assertRaises(ValueError, msg=bad[:20]):
                parse_int("x", bad)

    def test_numbers_inside_json_are_limited_too(self):
        parse_int("x", 999999999)
        for bad in (1000000000, 10 ** 30, -10 ** 30):
            with self.assertRaises(ValueError, msg=str(bad)[:12]):
                parse_int("x", bad)
        with self.assertRaises(ValueError):
            load_data(DependencyGraph(), {"tasks": [
                {"id": "a", "priority": 3, "deadline": "2026-11-01", "duration": 10 ** 30}]})

    def test_long_bad_value_is_not_echoed_in_full(self):
        with self.assertRaises(ValueError) as ctx:
            parse_int("days", "9" * 5000)
        self.assertLess(len(str(ctx.exception)), 200)

    @unittest.skipIf(sys.platform == "win32", "POSIX permission bits")
    def test_new_file_gets_normal_permissions_not_private_ones(self):
        with tempfile.TemporaryDirectory() as d:
            normal = Path(d) / "normal.txt"
            normal.write_text("x")
            saved = Path(d) / "saved.json"
            save_file(sample(), saved)
            self.assertEqual(stat.S_IMODE(saved.stat().st_mode), stat.S_IMODE(normal.stat().st_mode))

    @unittest.skipIf(sys.platform == "win32", "POSIX permission bits")
    def test_existing_file_keeps_its_permissions(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "t.json"
            save_file(sample(), path)
            os.chmod(path, 0o640)
            save_file(DependencyGraph(), path)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)

    def test_save_into_current_folder_with_bare_filename(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.getcwd()
            os.chdir(d)
            try:
                save_file(sample(), "bare.json")
                self.assertEqual(sorted(os.listdir(d)), ["bare.json"])
            finally:
                os.chdir(old)


if __name__ == "__main__":
    unittest.main()
