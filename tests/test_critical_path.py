import random
import unittest
from datetime import date

from scheduler.critical_path import critical_path
from scheduler.graph import DependencyGraph
from scheduler.scheduler import CycleError
from scheduler.task import Task

D = date(2026, 11, 1)


def build(durations, deps=()):
    """durations: {id: days}. deps: (task, needs) pairs."""
    g = DependencyGraph()
    for tid, days in durations.items():
        g.add_task(Task(tid, 3, D, days))
    for task_id, needs in deps:
        g.add_dependency(task_id, needs)
    return g


def result(g):
    path, total = critical_path(g)
    return [t.id for t in path], total


def brute_force_longest(g):
    """Independent check: try every path from every task with no prerequisites."""
    def longest_from(tid):
        nexts = g.dependents[tid]
        tail = max((longest_from(n) for n in nexts), default=0)
        return g.tasks[tid].duration + tail
    sources = [t for t in g.tasks if not g.prerequisites[t]]
    return max((longest_from(s) for s in sources), default=0)


class TestDuration(unittest.TestCase):
    def test_default_is_one_day(self):
        self.assertEqual(Task("a", 3, D).duration, 1)

    def test_zero_or_negative_rejected(self):
        for bad in (0, -2):
            with self.assertRaises(ValueError):
                Task("a", 3, D, bad)


class TestCriticalPath(unittest.TestCase):
    def test_empty_graph(self):
        self.assertEqual(result(DependencyGraph()), ([], 0))

    def test_single_task(self):
        self.assertEqual(result(build({"a": 4})), (["a"], 4))

    def test_chain(self):
        g = build({"a": 2, "b": 3, "c": 1}, [("b", "a"), ("c", "b")])
        self.assertEqual(result(g), (["a", "b", "c"], 6))

    def test_longer_branch_wins(self):
        # a -> b(1) -> d   and   a -> c(5) -> d
        g = build({"a": 1, "b": 1, "c": 5, "d": 1},
                  [("b", "a"), ("c", "a"), ("d", "b"), ("d", "c")])
        self.assertEqual(result(g), (["a", "c", "d"], 7))

    def test_independent_tasks_pick_longest(self):
        self.assertEqual(result(build({"a": 2, "b": 9, "c": 4})), (["b"], 9))

    def test_ties_resolved_by_smaller_id(self):
        g = build({"a": 2, "b": 2, "z": 1}, [("z", "a"), ("z", "b")])
        self.assertEqual(result(g), (["a", "z"], 3))

    def test_cycle_raises(self):
        g = build({"x": 1, "y": 1}, [("x", "y"), ("y", "x")])
        with self.assertRaises(CycleError):
            critical_path(g)

    def test_total_matches_brute_force_on_random_dags(self):
        rng = random.Random(7)
        for _ in range(100):
            n = rng.randint(1, 12)
            names = [f"t{i:02d}" for i in range(n)]
            g = build({x: rng.randint(1, 6) for x in names},
                      [(names[j], names[i]) for i in range(n)
                       for j in range(i + 1, n) if rng.random() < 0.3])
            path, total = critical_path(g)
            self.assertEqual(total, brute_force_longest(g))
            self.assertEqual(total, sum(t.duration for t in path))
            for before, after in zip(path, path[1:]):     # path uses real edges
                self.assertIn(before.id, g.prerequisites[after.id])


if __name__ == "__main__":
    unittest.main()
