import random
import unittest
from datetime import date

from scheduler.graph import DependencyGraph
from scheduler.scheduler import CycleError, schedule
from scheduler.task import Task


def build(tasks, deps=()):
    """tasks: (id, priority, deadline) tuples. deps: (task, needs) pairs."""
    g = DependencyGraph()
    for tid, pri, dl in tasks:
        g.add_task(Task(tid, pri, dl))
    for task_id, needs in deps:
        g.add_dependency(task_id, needs)
    return g


def ids(order):
    return [t.id for t in order]


D1, D2, D3 = date(2026, 11, 1), date(2026, 11, 2), date(2026, 11, 3)


class TestTask(unittest.TestCase):
    def test_empty_id_rejected(self):
        with self.assertRaises(ValueError):
            Task("  ", 3, D1)

    def test_priority_out_of_range_rejected(self):
        for bad in (0, 6, -1):
            with self.assertRaises(ValueError):
                Task("a", bad, D1)

    def test_priority_bounds_accepted(self):
        Task("a", 1, D1)
        Task("b", 5, D1)


class TestGraph(unittest.TestCase):
    def test_duplicate_task_rejected(self):
        g = build([("a", 1, D1)])
        with self.assertRaises(ValueError):
            g.add_task(Task("a", 2, D2))

    def test_unknown_task_rejected(self):
        g = build([("a", 1, D1)])
        with self.assertRaises(KeyError):
            g.add_dependency("a", "ghost")
        with self.assertRaises(KeyError):
            g.add_dependency("ghost", "a")

    def test_self_dependency_rejected(self):
        g = build([("a", 1, D1)])
        with self.assertRaises(ValueError):
            g.add_dependency("a", "a")

    def test_duplicate_dependency_counts_once(self):
        g = build([("a", 1, D1), ("b", 1, D1)])
        g.add_dependency("b", "a")
        g.add_dependency("b", "a")
        self.assertEqual(g.in_degree("b"), 1)


class TestGraphEditing(unittest.TestCase):
    def chain(self):
        return build([("a", 1, D1), ("b", 1, D1), ("c", 1, D1)],
                     [("b", "a"), ("c", "b")])

    def test_remove_dependency(self):
        g = self.chain()
        g.remove_dependency("b", "a")
        self.assertEqual(g.in_degree("b"), 0)
        self.assertNotIn("b", g.dependents["a"])

    def test_remove_missing_dependency_rejected(self):
        g = self.chain()
        with self.assertRaises(ValueError):
            g.remove_dependency("a", "b")
        with self.assertRaises(KeyError):
            g.remove_dependency("a", "ghost")

    def test_remove_task_cleans_both_sides(self):
        g = self.chain()
        g.remove_task("b")
        self.assertNotIn("b", g.tasks)
        self.assertEqual(g.dependents["a"], set())
        self.assertEqual(g.in_degree("c"), 0)
        self.assertEqual(ids(schedule(g)), ["a", "c"])

    def test_remove_unknown_task_rejected(self):
        with self.assertRaises(KeyError):
            self.chain().remove_task("ghost")

    def test_removing_a_link_breaks_a_cycle(self):
        g = build([("x", 1, D1), ("y", 1, D1)], [("x", "y"), ("y", "x")])
        with self.assertRaises(CycleError):
            schedule(g)
        g.remove_dependency("x", "y")
        self.assertEqual(ids(schedule(g)), ["x", "y"])

    def test_find_path(self):
        g = self.chain()
        self.assertEqual(g.find_path("a", "c"), ["a", "b", "c"])
        self.assertEqual(g.find_path("a", "a"), ["a"])
        self.assertIsNone(g.find_path("c", "a"))
        with self.assertRaises(KeyError):
            g.find_path("a", "ghost")

    def test_find_path_terminates_on_a_graph_that_already_has_a_loop(self):
        g = build([(c, 1, D1) for c in "abce"],
                  [("b", "a"), ("c", "b"), ("a", "c")])      # a -> b -> c -> a, e separate
        self.assertIsNone(g.find_path("a", "e"))
        self.assertEqual(g.find_path("a", "c"), ["a", "b", "c"])

    def test_find_path_picks_a_shortest_chain(self):
        g = build([(c, 1, D1) for c in "abcd"],
                  [("b", "a"), ("c", "b"), ("d", "c"), ("d", "a")])
        self.assertEqual(g.find_path("a", "d"), ["a", "d"])


def assert_consistent(test, g):
    """Both adjacency maps agree with each other and with the task list."""
    test.assertEqual(set(g.dependents), set(g.tasks))
    test.assertEqual(set(g.prerequisites), set(g.tasks))
    for tid, task in g.tasks.items():
        test.assertEqual(task.id, tid)
    for tid, needs in g.prerequisites.items():
        for n in needs:
            test.assertIn(n, g.tasks)
            test.assertIn(tid, g.dependents[n])
    for tid, waiting in g.dependents.items():
        for w in waiting:
            test.assertIn(tid, g.prerequisites[w])


class TestReplaceTask(unittest.TestCase):
    def graph(self):
        return build([("a", 1, D1), ("b", 2, D2), ("c", 3, D3)], [("b", "a"), ("c", "b")])

    def test_update_without_rename_keeps_links_and_position(self):
        g = self.graph()
        g.replace_task("b", Task("b", 5, D3, 4))
        self.assertEqual(list(g.tasks), ["a", "b", "c"])
        self.assertEqual((g.tasks["b"].priority, g.tasks["b"].deadline, g.tasks["b"].duration), (5, D3, 4))
        self.assertEqual(g.prerequisites["b"], {"a"})
        self.assertEqual(g.dependents["b"], {"c"})
        assert_consistent(self, g)

    def test_rename_updates_every_link_from_both_sides(self):
        g = self.graph()
        g.replace_task("b", Task("B2", 5, D1, 4))
        self.assertEqual(list(g.tasks), ["a", "B2", "c"])           # same position
        self.assertEqual(g.prerequisites["B2"], {"a"})
        self.assertEqual(g.dependents["a"], {"B2"})
        self.assertEqual(g.prerequisites["c"], {"B2"})
        self.assertEqual(g.dependents["B2"], {"c"})
        self.assertNotIn("b", g.tasks)
        self.assertNotIn("b", g.dependents)
        self.assertNotIn("b", g.prerequisites)
        assert_consistent(self, g)

    def test_case_only_rename_is_allowed(self):
        g = self.graph()
        g.replace_task("a", Task("A", 1, D1))
        self.assertEqual(list(g.tasks), ["A", "b", "c"])
        self.assertEqual(g.prerequisites["b"], {"A"})

    def test_rename_onto_an_existing_task_is_refused_and_changes_nothing(self):
        g = self.graph()
        with self.assertRaises(ValueError):
            g.replace_task("a", Task("c", 1, D1))
        self.assertEqual(list(g.tasks), ["a", "b", "c"])
        self.assertEqual(g.tasks["a"].priority, 1)
        assert_consistent(self, g)

    def test_unknown_task_is_refused(self):
        with self.assertRaises(KeyError):
            self.graph().replace_task("ghost", Task("x", 1, D1))

    def test_schedule_is_the_same_apart_from_the_new_name(self):
        g = build([("a", 3, D2), ("b", 3, D1), ("c", 3, D3), ("d", 3, D1)],
                  [("c", "a"), ("c", "b"), ("d", "c")])
        before = ids(schedule(g))
        g.replace_task("b", Task("renamed", 3, D1))
        self.assertEqual(ids(schedule(g)), ["renamed" if x == "b" else x for x in before])

    def test_changing_a_deadline_changes_the_order(self):
        g = build([("a", 3, D2), ("b", 3, D3)])
        self.assertEqual(ids(schedule(g)), ["a", "b"])
        g.replace_task("b", Task("b", 3, D1))
        self.assertEqual(ids(schedule(g)), ["b", "a"])

    def test_random_edits_keep_the_graph_consistent(self):
        rng = random.Random(11)
        for _ in range(200):
            n = rng.randint(2, 10)
            names = [f"t{i}" for i in range(n)]
            g = build([(x, rng.randint(1, 5), D1) for x in names],
                      [(names[j], names[i]) for i in range(n) for j in range(i + 1, n) if rng.random() < .3])
            edges = sum(len(v) for v in g.prerequisites.values())
            for k in range(rng.randint(1, 8)):
                old = rng.choice(list(g.tasks))
                new_id = rng.choice([old, f"n{rng.randint(0, 99)}"])
                try:
                    g.replace_task(old, Task(new_id, rng.randint(1, 5), D2, rng.randint(1, 4)))
                except ValueError:
                    pass                                    # the name was taken: nothing changes
                assert_consistent(self, g)
            self.assertEqual(sum(len(v) for v in g.prerequisites.values()), edges)   # no link lost or invented
            self.assertEqual(len(ids(schedule(g))), n)


class TestOrdering(unittest.TestCase):
    def test_empty_graph(self):
        self.assertEqual(schedule(DependencyGraph()), [])

    def test_earlier_deadline_first(self):
        g = build([("late", 3, D3), ("early", 3, D1), ("mid", 3, D2)])
        self.assertEqual(ids(schedule(g)), ["early", "mid", "late"])

    def test_priority_breaks_deadline_tie(self):
        g = build([("low", 1, D1), ("high", 5, D1)])
        self.assertEqual(ids(schedule(g)), ["high", "low"])

    def test_id_breaks_full_tie(self):
        g = build([("b", 3, D1), ("a", 3, D1)])
        self.assertEqual(ids(schedule(g)), ["a", "b"])

    def test_dependency_beats_deadline(self):
        g = build(
            [("deploy", 5, D1), ("test", 3, D2), ("build", 3, D3)],
            [("test", "build"), ("deploy", "test")],
        )
        self.assertEqual(ids(schedule(g)), ["build", "test", "deploy"])

    def test_task_with_two_prerequisites_waits_for_both(self):
        g = build(
            [("a", 3, D2), ("b", 3, D3), ("c", 3, D1)],
            [("c", "a"), ("c", "b")],
        )
        order = ids(schedule(g))
        self.assertEqual(order[-1], "c")

    def test_graph_not_modified_by_scheduling(self):
        g = build([("a", 1, D1), ("b", 1, D2)], [("b", "a")])
        first = ids(schedule(g))
        self.assertEqual(g.in_degree("b"), 1)
        self.assertEqual(ids(schedule(g)), first)

    def test_random_dags_respect_every_dependency(self):
        rng = random.Random(42)
        for _ in range(50):
            n = rng.randint(2, 30)
            names = [f"t{i}" for i in range(n)]
            tasks = [(x, rng.randint(1, 5), date(2026, 11, rng.randint(1, 28)))
                     for x in names]
            # edges only go from lower to higher index, so the graph is acyclic
            deps = [(names[j], names[i]) for i in range(n)
                    for j in range(i + 1, n) if rng.random() < 0.2]
            order = ids(schedule(build(tasks, deps)))
            self.assertEqual(sorted(order), sorted(names))   # each task exactly once
            pos = {t: k for k, t in enumerate(order)}
            for task_id, needs in deps:
                self.assertLess(pos[needs], pos[task_id])


class TestCycles(unittest.TestCase):
    def test_two_task_cycle(self):
        g = build([("x", 1, D1), ("y", 1, D1)], [("x", "y"), ("y", "x")])
        with self.assertRaises(CycleError) as ctx:
            schedule(g)
        self.assertEqual(set(ctx.exception.cycle), {"x", "y"})
        self.assertEqual(ctx.exception.blocked, [])

    def test_blocked_tasks_separated_from_cycle(self):
        g = build(
            [(c, 3, D1) for c in "abcde"],
            [("a", "c"), ("b", "a"), ("c", "b"), ("d", "c")],
        )
        with self.assertRaises(CycleError) as ctx:
            schedule(g)
        err = ctx.exception
        self.assertEqual(set(err.cycle), {"a", "b", "c"})
        self.assertEqual(err.blocked, ["d"])
        self.assertEqual(err.cycle[0], err.cycle[-1])        # loop is closed

    def test_reported_cycle_follows_real_edges(self):
        g = build(
            [(c, 3, D1) for c in "abc"],
            [("a", "c"), ("b", "a"), ("c", "b")],
        )
        with self.assertRaises(CycleError) as ctx:
            schedule(g)
        cyc = ctx.exception.cycle
        for before, after in zip(cyc, cyc[1:]):
            self.assertIn(before, g.prerequisites[after])

    def test_independent_task_does_not_hide_cycle(self):
        g = build(
            [("free", 5, D1), ("x", 1, D1), ("y", 1, D1)],
            [("x", "y"), ("y", "x")],
        )
        with self.assertRaises(CycleError):
            schedule(g)


if __name__ == "__main__":
    unittest.main()
