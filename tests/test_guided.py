import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scheduler.graph import DependencyGraph
from scheduler.guided import NUM, GuidedApp, arrow
from scheduler.scheduler import schedule
from scheduler.storage import load_file
from scheduler.task import Task

ROOT = Path(__file__).resolve().parent.parent
ADD, LIST, PLAN, CHAIN, CHANGE, LINK, RM_TASK, RM_LINK, EXAMPLE, SAVE = (
    NUM[k] for k in ("add", "list", "plan", "chain", "change", "link",
                     "remove_task", "remove_link", "example", "save"))
TODAY = date(2026, 10, 3)
_open_sessions = []


def tearDownModule():
    """Remove every temp folder even when a test failed before calling close()."""
    for s in _open_sessions:
        s.close()


class Session:
    """Feeds scripted answers to the app and records everything it prints."""

    def __init__(self, answers, graph=None, data_path=None, offer_saved=False):
        self.answers = list(answers)
        self.out = []
        self.dir = tempfile.TemporaryDirectory()
        _open_sessions.append(self)
        self.path = data_path or str(Path(self.dir.name) / "my_tasks.json")
        self.app = GuidedApp(graph, ask=self._ask, say=self.out.append,
                             today=lambda: TODAY, data_path=self.path)
        self.offer_saved = offer_saved

    def _ask(self, prompt):
        self.out.append(prompt)
        if not self.answers:
            raise EOFError
        return self.answers.pop(0)

    def run(self):
        self.app.run(offer_saved=self.offer_saved)
        return self

    @property
    def text(self):
        return "\n".join(self.out)

    @property
    def graph(self):
        return self.app.graph

    def close(self):
        try:
            self.dir.cleanup()
        except OSError:
            pass


def session(answers, **kw):
    s = Session(answers, **kw)
    s.run()
    return s


ADD_A = ["1", "Write report", "high", "5 nov", "2"]          # then blockers prompt may follow


class TestAddTask(unittest.TestCase):
    def test_adds_task_with_friendly_inputs(self):
        s = session(["1", "Write report", "high", "5 nov", "2", "0", "n"])
        t = s.graph.tasks["Write report"]
        self.assertEqual((t.priority, t.deadline, t.duration), (4, date(2026, 11, 5), 2))
        self.assertIn("Thu 05 Nov 2026", s.text)
        s.close()

    def test_defaults_when_enter_pressed(self):
        s = session(["1", "Quick", "", "tomorrow", "", "0", "n"])
        t = s.graph.tasks["Quick"]
        self.assertEqual((t.priority, t.deadline, t.duration), (3, date(2026, 10, 4), 1))
        s.close()

    def test_bad_answers_are_reasked_not_fatal(self):
        s = session(["1", "", "5", "a,b", "Real", "99", "banana", "urgent",
                     "soon", "31 feb", "friday", "zero", "0", "-2", "3", "0", "n"])
        t = s.graph.tasks["Real"]
        self.assertEqual((t.priority, t.deadline, t.duration), (5, date(2026, 10, 9), 3))
        for msg in ("needs a name", "include a word", "commas", "Please type a number from 1",
                    "couldn't read that date", "doesn't exist", "whole number of days",
                    "at least 1 day"):
            self.assertIn(msg, s.text)
        s.close()

    def test_duplicate_name_rejected_case_insensitively(self):
        s = session(["1", "Build", "3", "tomorrow", "1", "1", "build", "Test", "3", "tomorrow", "1", "", "0", "n"])
        self.assertEqual(list(s.graph.tasks), ["Build", "Test"])
        self.assertIn("already have a task called 'build'", s.text)
        s.close()

    def test_blockers_by_number_and_name(self):
        g = DependencyGraph()
        s0 = session(["1", "A", "3", "tomorrow", "1", "1", "B", "3", "tomorrow", "1", "1",
                      "1", "C", "3", "tomorrow", "1", "1, b", "0", "n"], graph=g)
        self.assertEqual(s0.graph.prerequisites["C"], {"A", "B"})
        s0.close()

    def test_blockers_ignore_blanks_and_duplicates(self):
        s = session(["1", "A", "3", "tomorrow", "1",
                     "1", "B", "3", "tomorrow", "1", "1, ,a,1,", "0", "n"])
        self.assertEqual(s.graph.prerequisites["B"], {"A"})
        self.assertEqual(s.text.count("Waits for: A."), 1)
        s.close()

    def test_unknown_blocker_reasked(self):
        s = session(["1", "A", "3", "tomorrow", "1",
                     "1", "B", "3", "tomorrow", "1", "zzz", "1", "0", "n"])
        self.assertEqual(s.graph.prerequisites["B"], {"A"})
        self.assertIn("I don't see: zzz", s.text)
        s.close()

    def test_cancel_at_any_question_changes_nothing(self):
        for answers in (["1", "cancel"], ["1", "X", "cancel"], ["1", "X", "3", "cancel"],
                        ["1", "X", "3", "tomorrow", "back"]):
            s = session(answers + ["0"])
            self.assertEqual(s.graph.tasks, {}, answers)
            self.assertIn("Cancelled", s.text)
            s.close()

    def test_past_date_is_flagged_but_allowed(self):
        s = session(["1", "Late", "3", "2026-09-01", "1", "0", "y"])
        self.assertIn("already passed", s.text)
        self.assertIn("Late", s.graph.tasks)
        s.close()


class TestViewing(unittest.TestCase):
    def test_empty_states_point_to_next_step(self):
        s = session([LIST, PLAN, CHAIN, CHANGE, LINK, RM_TASK, RM_LINK, "0"])
        self.assertIn("no tasks yet", s.text)
        self.assertIn("at least two tasks", s.text)
        self.assertIn("no tasks to remove", s.text)
        self.assertIn("nothing to remove", s.text)
        s.close()

    def test_example_plan_explains_itself(self):
        s = session([EXAMPLE, PLAN, "0"])
        self.assertIn("1. lint", s.text)
        self.assertIn("5. deploy", s.text)
        self.assertIn("after: test", s.text)
        self.assertIn("Heads-up: 'test' must be finished before 'deploy'", s.text)
        self.assertEqual(s.text.count("Heads-up"), 1)          # build -> test is consistent
        self.assertIn("How the order is chosen", s.text)
        s.close()

    def test_longest_chain_explains_both_totals(self):
        s = session([EXAMPLE, CHAIN, "0"])
        self.assertIn("build → test → deploy  (6 days)", s.text)
        self.assertIn("one thing at a time, everything takes 8 days", s.text)
        s.close()

    def test_no_heads_up_when_dates_are_consistent(self):
        s = session(["1", "A", "3", "1 nov", "1", "1", "B", "3", "5 nov", "1", "1", "3", "0", "n"])
        self.assertNotIn("Heads-up", s.text)
        s.close()

    def test_list_shows_waits_for(self):
        s = session([EXAMPLE, LIST, "0"])
        self.assertIn("waits for: build", s.text)
        s.close()


class TestLinks(unittest.TestCase):
    def two(self, *more):
        return ["1", "A", "3", "1 nov", "1", "1", "B", "3", "2 nov", "1", ""] + list(more) + ["0", "n"]

    def test_link_by_number_and_name(self):
        s = session(self.two(LINK, "b", "a"))
        self.assertEqual(s.graph.prerequisites["B"], {"A"})
        s.close()

    def test_loop_refused_with_path(self):
        s = session(self.two(LINK, "2", "1", LINK, "1", "2"))
        self.assertIn("create a loop", s.text)
        self.assertEqual(s.graph.prerequisites["A"], set())
        self.assertEqual([t.id for t in schedule(s.graph)], ["A", "B"])
        s.close()

    def test_self_and_duplicate_links(self):
        s = session(self.two(LINK, "1", "1", "2", LINK, "1", "2"))
        self.assertIn("can't wait for itself", s.text)
        self.assertIn("already waits for", s.text)
        s.close()

    def test_remove_link(self):
        s = session([EXAMPLE, RM_LINK, "1", "0", "y"])
        self.assertEqual(sum(len(v) for v in s.graph.prerequisites.values()), 1)
        self.assertIn("no longer waits for", s.text)
        s.close()

    def test_remove_link_bad_number_reasked(self):
        s = session([EXAMPLE, RM_LINK, "9", "x", "1", "0", "y"])
        self.assertIn("number from 1 to 2", s.text)
        s.close()


class TestUnsavedTracking(unittest.TestCase):
    """Every change must make quitting offer to save; saving must clear that."""

    def assert_offers_save(self, answers):
        s = session(answers + ["0", "n"])
        self.assertIn("unsaved changes", s.text, answers)
        s.close()

    def test_every_kind_of_change_counts_as_unsaved(self):
        self.assert_offers_save(["1", "X", "3", "tomorrow", "1"])          # add task
        self.assert_offers_save([EXAMPLE, LINK, "lint", "docs"])                # add link
        self.assert_offers_save([EXAMPLE, RM_TASK, "lint", "y"])                   # remove task
        self.assert_offers_save([EXAMPLE, RM_LINK, "1"])                           # remove link

    def test_declined_or_cancelled_changes_do_not_count(self):
        for answers in ([EXAMPLE, RM_TASK, "lint", "n"], [EXAMPLE, LINK, "lint", "cancel"],
                        [EXAMPLE, LINK, "1", "2", LINK, "x"]):
            s = session(answers + ["0"])
            self.assertNotIn("unsaved", s.text, answers)
            s.close()

    def test_saving_clears_the_flag(self):
        s = session(["1", "X", "3", "tomorrow", "1", SAVE, "0"])
        self.assertEqual(s.text.count("unsaved changes"), 0)
        self.assertIn("Goodbye.", s.text)
        self.assertEqual(s.answers, [])
        s.close()

    def test_change_after_saving_counts_again(self):
        s = session(["1", "X", "3", "tomorrow", "1", SAVE,
                     "1", "Y", "3", "tomorrow", "1", "", "0", "n"])
        self.assertEqual(s.text.count("unsaved changes"), 1)
        s.close()


class TestChangeTask(unittest.TestCase):
    """The example has: build, test (waits build), deploy (waits test), docs, lint."""

    def change(self, pick, *answers, tail=("0", "n")):
        """Load the example, change one task. Answers: name, importance, due, days, waits-for."""
        return session([EXAMPLE, CHANGE, pick, *answers, *tail])

    def test_pressing_enter_everywhere_changes_nothing(self):
        s = self.change("test", "", "", "", "", "", tail=("0",))
        self.assertIn("Nothing was changed", s.text)
        self.assertNotIn("unsaved", s.text)
        self.assertEqual(s.graph.tasks["test"], Task("test", 4, date(2026, 11, 6), 2))
        s.close()

    def test_shows_current_values_as_defaults(self):
        s = self.change("test", "", "", "", "", "", tail=("0",))
        for shown in ("[test]", "[4]", "[Fri 06 Nov 2026]", "[2]", "Right now: build"):
            self.assertIn(shown, s.text)
        s.close()

    def test_change_importance_only(self):
        s = self.change("docs", "", "5", "", "", "")
        self.assertEqual(s.graph.tasks["docs"].priority, 5)
        self.assertIn(f"importance: 2 {arrow()} 5", s.text)
        self.assertNotIn("name:", s.text.split("Changed")[-1])
        s.close()

    def test_change_due_date_with_a_friendly_date(self):
        s = self.change("docs", "", "", "6 nov", "", "")
        self.assertEqual(s.graph.tasks["docs"].deadline, date(2026, 11, 6))
        self.assertIn("Due date: Fri 06 Nov 2026", s.text)
        s.close()

    def test_change_days(self):
        s = self.change("docs", "", "", "", "4", "")
        self.assertEqual(s.graph.tasks["docs"].duration, 4)
        s.close()

    def test_pick_by_number_or_by_name_in_any_case(self):
        for pick in ("4", "docs", "DOCS"):
            s = self.change(pick, "", "5", "", "", "")
            self.assertEqual(s.graph.tasks["docs"].priority, 5, pick)
            s.close()

    def test_rename_keeps_position_and_every_link(self):
        s = self.change("test", "verify", "", "", "", "")
        g = s.graph
        self.assertEqual(list(g.tasks), ["build", "verify", "deploy", "docs", "lint"])
        self.assertEqual(g.prerequisites["verify"], {"build"})
        self.assertEqual(g.prerequisites["deploy"], {"verify"})       # others still wait for it
        self.assertEqual([t.id for t in schedule(g)], ["lint", "docs", "build", "verify", "deploy"])
        s.close()

    def test_rename_to_a_taken_name_is_reasked_in_any_case(self):
        s = self.change("build", "TEST", "compile", "", "", "", "")
        self.assertIn("already have a task called 'TEST'", s.text)
        self.assertIn("compile", s.graph.tasks)
        s.close()

    def test_changing_only_the_letter_case_of_the_name_is_allowed(self):
        s = self.change("lint", "Lint", "", "", "", "")
        self.assertIn("Lint", s.graph.tasks)
        self.assertNotIn("lint", s.graph.tasks)
        s.close()

    def test_bad_values_are_reasked_and_the_defaults_survive_blank_answers(self):
        # name: bad then keep; importance: bad then keep; due: bad then keep; days: two bad then keep; waits: keep
        s = self.change("docs", "a,b", "", "99", "", "soon", "", "0", "x", "", "")
        self.assertIn("leave out commas", s.text)
        self.assertIn("Please type a number from 1", s.text)
        self.assertIn("couldn't read that date", s.text)
        self.assertIn("at least 1 day", s.text)
        self.assertEqual(s.graph.tasks["docs"], Task("docs", 2, date(2026, 11, 2), 1))
        s.close()

    def test_waits_for_can_be_kept_cleared_replaced_and_extended(self):
        s = self.change("test", "", "", "", "", "none")
        self.assertEqual(s.graph.prerequisites["test"], set())
        self.assertEqual(s.graph.prerequisites["deploy"], {"test"})
        s.close()
        s = self.change("deploy", "", "", "", "", "build")
        self.assertEqual(s.graph.prerequisites["deploy"], {"build"})
        self.assertEqual(s.graph.dependents["test"], set())
        s.close()
        s = self.change("docs", "", "", "", "", "build, 5")
        self.assertEqual(s.graph.prerequisites["docs"], {"build", "lint"})
        s.close()
        s = self.change("deploy", "", "", "", "", "")                  # Enter keeps
        self.assertEqual(s.graph.prerequisites["deploy"], {"test"})
        s.close()

    def test_a_link_that_would_make_a_loop_is_refused_and_reasked(self):
        s = self.change("build", "", "", "", "", "deploy", "lint")
        self.assertIn("'build' can't wait for 'deploy'", s.text)
        self.assertIn(f"build {arrow()} test {arrow()} deploy", s.text)
        self.assertEqual(s.graph.prerequisites["build"], {"lint"})
        self.assertEqual(len(schedule(s.graph)), 5)                    # still a valid plan
        s.close()

    def test_waiting_for_itself_is_refused(self):
        s = self.change("docs", "", "", "", "", "docs", "none")
        self.assertIn("can't wait for itself", s.text)
        s.close()

    def test_unknown_task_in_waits_for_is_reasked(self):
        s = self.change("docs", "", "", "", "", "zzz", "none")
        self.assertIn("I don't see: zzz", s.text)
        s.close()

    def test_a_task_actually_named_none_can_be_chosen(self):
        g = DependencyGraph()
        for name in ("A", "none", "B"):
            g.add_task(Task(name, 3, date(2026, 11, 1)))
        s = session([CHANGE, "B", "", "", "", "", "none", "0", "n"], graph=g)
        self.assertEqual(s.graph.prerequisites["B"], {"none"})
        s.close()

    def test_a_name_containing_a_comma_can_be_chosen_by_name(self):
        g = DependencyGraph()
        for name in ("Send, final", "B"):
            g.add_task(Task(name, 3, date(2026, 11, 1)))
        s = session([CHANGE, "B", "", "", "", "", "Send, final", "0", "n"], graph=g)
        self.assertEqual(s.graph.prerequisites["B"], {"Send, final"})
        s.close()

    def test_cancelling_part_way_changes_nothing(self):
        for cancel_at in range(1, 6):
            answers = ["compile", "5", "9 nov", "3", "none"][:cancel_at - 1] + ["cancel"]
            s = session([EXAMPLE, CHANGE, "build", *answers, "0"])
            self.assertEqual(s.graph.tasks["build"], Task("build", 3, date(2026, 11, 5), 3), answers)
            self.assertEqual(s.graph.prerequisites["test"], {"build"}, answers)
            self.assertIn("Cancelled", s.text)
            self.assertNotIn("unsaved", s.text)
            s.close()

    def test_unknown_task_is_reasked(self):
        s = session([EXAMPLE, CHANGE, "zzz", "", "docs", "", "", "", "", "", "0"])
        self.assertIn("I don't see 'zzz'", s.text)
        s.close()

    def test_empty_list_points_to_next_step(self):
        s = session([CHANGE, "0"])
        self.assertIn("no tasks yet", s.text)
        s.close()

    def test_a_single_task_is_not_asked_what_it_waits_for(self):
        s = session(["1", "Solo", "3", "tomorrow", "1", CHANGE, "Solo", "", "5", "", "", "0", "n"])
        self.assertEqual(s.graph.tasks["Solo"].priority, 5)
        self.assertNotIn("What does it wait for", s.text)
        s.close()

    def test_a_change_counts_as_unsaved_and_saving_clears_it(self):
        s = self.change("docs", "", "5", "", "", "")
        self.assertIn("unsaved changes", s.text)
        s.close()
        s = session([EXAMPLE, CHANGE, "docs", "", "5", "", "", "", SAVE, "0"])
        self.assertNotIn("unsaved", s.text)
        s.close()

    def test_changes_survive_save_and_reload(self):
        s = session([EXAMPLE, CHANGE, "test", "verify", "5", "9 nov", "3", "none", SAVE, "0"])
        s2 = Session(["y", "0"], data_path=s.path, offer_saved=True).run()
        t = s2.graph.tasks["verify"]
        self.assertEqual((t.priority, t.deadline, t.duration), (5, date(2026, 11, 9), 3))
        self.assertEqual(s2.graph.prerequisites["verify"], set())
        self.assertEqual(s2.graph.prerequisites["deploy"], {"verify"})
        s.close()
        s2.close()

    def test_plan_and_longest_chain_use_the_changed_values(self):
        s = session([EXAMPLE, CHANGE, "build", "", "", "", "10", "", CHAIN, "0", "n"])
        self.assertIn(f"build {arrow()} test {arrow()} deploy  (13 days)", s.text)
        s.close()

    def test_changing_a_loaded_cycle_task_still_works(self):
        g = DependencyGraph()
        load_file(g, ROOT / "examples" / "cycle.json")
        s = session([CHANGE, "d", "", "5", "", "", "", "0", "n"], graph=g)
        self.assertEqual(s.graph.tasks["d"].priority, 5)
        s.close()


class TestSavingSafely(unittest.TestCase):
    """Saving must never silently replace a saved list the user chose not to load."""

    def make_saved(self):
        s = session([EXAMPLE, SAVE, "0"])
        return s

    def test_declining_the_saved_list_then_saving_asks_before_replacing(self):
        first = self.make_saved()
        s = Session(["n", "1", "Only one", "3", "tomorrow", "1", SAVE, "n", "0", "n"],
                    data_path=first.path, offer_saved=True).run()
        self.assertIn("already holds 5 saved tasks", s.text)
        self.assertIn("nothing was saved", s.text)
        h = DependencyGraph()
        load_file(h, first.path)
        self.assertEqual(len(h.tasks), 5)                       # the old file is untouched
        first.close()
        s.close()

    def test_agreeing_replaces_it_and_later_saves_do_not_ask_again(self):
        first = self.make_saved()
        # save (agree), then add another task and save again: the file is ours now, so no second question
        s = Session(["n", "1", "Only one", "3", "tomorrow", "1", SAVE, "y",
                     "1", "Second", "3", "tomorrow", "1", "", SAVE, "0"],
                    data_path=first.path, offer_saved=True).run()
        h = DependencyGraph()
        load_file(h, first.path)
        self.assertEqual(list(h.tasks), ["Only one", "Second"])
        self.assertEqual(s.text.count("already holds"), 1)
        first.close()
        s.close()

    def test_loading_the_saved_list_then_saving_does_not_ask(self):
        first = self.make_saved()
        s = Session(["y", "1", "Extra", "3", "tomorrow", "1", "", SAVE, "0"],
                    data_path=first.path, offer_saved=True).run()
        self.assertNotIn("already holds", s.text)
        first.close()
        s.close()

    def test_an_existing_empty_list_is_replaced_without_asking(self):
        s = Session(["1", "X", "3", "tomorrow", "1", SAVE, "0"])
        Path(s.path).write_text('{"tasks": [], "dependencies": []}')
        s.run()
        self.assertNotIn("already holds", s.text)
        self.assertIn("Saved 1 task", s.text)
        s.close()

    def test_saving_identical_content_does_not_ask(self):
        first = self.make_saved()
        s = Session([EXAMPLE, SAVE, "0"], data_path=first.path).run()
        self.assertNotIn("already holds", s.text)
        first.close()
        s.close()

    def test_an_unreadable_existing_file_is_not_replaced_without_asking(self):
        s = Session(["1", "X", "3", "tomorrow", "1", SAVE, "n", "0", "n"])
        Path(s.path).write_text("{not json")
        s.run()
        self.assertIn("can't be read as a task list", s.text)
        self.assertEqual(Path(s.path).read_text(), "{not json")
        s.close()

    def test_quit_flow_respects_a_refused_replacement(self):
        first = self.make_saved()
        s = Session(["n", "1", "Only one", "3", "tomorrow", "1", "0", "y", "n", "y"],
                    data_path=first.path, offer_saved=True).run()
        h = DependencyGraph()
        load_file(h, first.path)
        self.assertEqual(len(h.tasks), 5)
        self.assertIn("Quit anyway?", s.text)
        first.close()
        s.close()


class TestRemoveTask(unittest.TestCase):
    def test_remove_confirmed_unblocks_dependents(self):
        s = session([EXAMPLE, RM_TASK, "build", "y", "0", "y"])
        self.assertNotIn("build", s.graph.tasks)
        self.assertEqual(s.graph.prerequisites["test"], set())
        self.assertIn("test will no longer wait for it", s.text)
        s.close()

    def test_remove_declined_keeps_task(self):
        s = session([EXAMPLE, RM_TASK, "1", "n", "0"])
        self.assertIn("build", s.graph.tasks)
        self.assertIn("nothing was removed", s.text)
        s.close()


class TestSaveAndLoad(unittest.TestCase):
    def test_save_then_reload_in_new_session(self):
        s = session([EXAMPLE, "1", "Extra", "5", "tomorrow", "2", "", SAVE, "0"])
        self.assertIn("Saved 6 tasks", s.text)
        s2 = Session(["y", "2", "0"], data_path=s.path, offer_saved=True).run()
        self.assertIn("Found 6 saved tasks", s2.text)
        self.assertIn("Extra", s2.graph.tasks)
        s.close(); s2.close()

    def test_declining_saved_file_starts_empty_and_keeps_file(self):
        s = session([EXAMPLE, SAVE, "0"])
        s2 = Session(["n", "0"], data_path=s.path, offer_saved=True).run()
        self.assertEqual(s2.graph.tasks, {})
        self.assertTrue(Path(s.path).exists())
        s.close(); s2.close()

    def test_corrupt_saved_file_is_reported_not_fatal(self):
        s = Session(["0"], offer_saved=True)
        Path(s.path).write_text("{oops")
        s.run()
        self.assertIn("couldn't read it", s.text)
        s.close()

    def test_quit_prompts_to_save_unsaved_changes(self):
        s = session([EXAMPLE, "1", "X", "3", "tomorrow", "1", "", "0", "y"])
        self.assertIn("unsaved changes", s.text)
        self.assertTrue(Path(s.path).exists())
        h = DependencyGraph(); load_file(h, s.path)
        self.assertIn("X", h.tasks)
        s.close()

    def test_quit_without_saving_when_declined(self):
        s = session(["1", "X", "3", "tomorrow", "1", "0", "n"])
        self.assertFalse(Path(s.path).exists())
        s.close()

    def test_no_prompt_when_nothing_changed(self):
        s = session([EXAMPLE, "0"])             # the example alone is not "unsaved work"
        self.assertNotIn("unsaved", s.text)
        s.close()

    def test_failed_save_offers_to_stay(self):
        s = Session(["1", "X", "3", "tomorrow", "1", "0", "y", "n", SAVE, "0", "n"],
                    data_path="/nonexistent-folder-xyz/t.json").run()
        self.assertIn("Couldn't save", s.text)
        self.assertIn("Quit anyway?", s.text)
        s.close()


class TestRobustness(unittest.TestCase):
    def test_bad_menu_choices(self):
        s = session(["", "abc", "42", "-1", "?", "0"])
        self.assertEqual(s.text.count("Please type a number from the menu"), 4)
        self.assertIn("How this works", s.text)
        s.close()

    def test_end_of_input_exits_cleanly(self):
        s = session([])
        self.assertIn("Goodbye", s.text)
        s.close()

    def test_end_of_input_mid_question_exits_cleanly(self):
        s = session(["1", "Half done"])
        self.assertIn("Goodbye", s.text)
        self.assertEqual(s.graph.tasks, {})
        s.close()

    def test_keyboard_interrupt_exits_cleanly(self):
        def boom(prompt):
            raise KeyboardInterrupt
        out = []
        GuidedApp(ask=boom, say=out.append).run(offer_saved=False)
        self.assertIn("Goodbye.", out)

    def test_example_refuses_to_overwrite(self):
        s = session(["1", "Mine", "3", "tomorrow", "1", EXAMPLE, "0", "n"])
        self.assertIn("only loads into an empty list", s.text)
        self.assertEqual(list(s.graph.tasks), ["Mine"])
        s.close()

    def test_loaded_cycle_is_explained_in_plain_words(self):
        g = DependencyGraph()
        load_file(g, ROOT / "examples" / "cycle.json")
        s = session(["3", "4", "0"], graph=g)
        self.assertIn("waiting on each other", s.text)
        self.assertIn("b → c → a → b", s.text)
        self.assertIn("Also stuck because of that: d", s.text)
        self.assertIn("removing one link", s.text)
        s.close()

    def test_fix_a_loaded_cycle_through_the_menu(self):
        g = DependencyGraph()
        load_file(g, ROOT / "examples" / "cycle.json")
        s = session([RM_LINK, "1", "3", "0"], graph=g)
        self.assertNotIn("waiting on each other", s.text.split("Removed.")[-1])
        self.assertIn("Your plan", s.text)
        s.close()


class TestOddInput(unittest.TestCase):
    def test_enter_accepts_the_default_on_yes_no(self):
        s = session(["1", "X", "3", "tomorrow", "1", "0", ""])      # default is "save"
        self.assertTrue(Path(s.path).exists())
        s.close()

    def test_unclear_yes_no_is_reasked(self):
        s = session(["1", "X", "3", "tomorrow", "1", "0", "maybe", "n"])
        self.assertIn("Please answer y or n", s.text)
        self.assertFalse(Path(s.path).exists())
        s.close()

    def test_blank_or_unknown_pick_is_reasked(self):
        s = session([EXAMPLE, RM_TASK, "", "zzz", "lint", "y", "0", "y"])
        self.assertIn("type a number or a name", s.text)
        self.assertIn("I don't see 'zzz'", s.text)
        self.assertNotIn("lint", s.graph.tasks)
        s.close()

    def test_blank_due_date_is_reasked(self):
        s = session(["1", "X", "3", "", "tomorrow", "1", "0", "n"])
        self.assertIn("A due date is needed", s.text)
        self.assertIn("X", s.graph.tasks)
        s.close()

    def test_empty_saved_file_is_ignored_quietly(self):
        s = Session(["0"], offer_saved=True)
        Path(s.path).write_text('{"tasks": []}')
        s.run()
        self.assertNotIn("Found", s.text)
        s.close()

    def test_saved_file_not_offered_over_existing_tasks(self):
        g = DependencyGraph()
        load_file(g, ROOT / "examples" / "tasks.json")
        s = Session(["0"], graph=g, offer_saved=True)
        Path(s.path).write_text('{"tasks": [{"id": "z", "priority": 1, "deadline": "2026-01-01"}]}')
        s.run()
        self.assertNotIn("Found", s.text)
        self.assertEqual(len(s.graph.tasks), 5)
        s.close()

    def test_two_task_cycle_has_no_stuck_line(self):
        g = DependencyGraph()
        load_file(g, ROOT / "examples" / "cycle.json")
        g.remove_task("d")
        s = session(["3", "0"], graph=g)
        self.assertIn("waiting on each other", s.text)
        self.assertNotIn("Also stuck", s.text)
        s.close()

    def test_example_load_failure_is_reported(self):
        import scheduler.guided as guided
        original = guided.DEMO_FILE
        guided.DEMO_FILE = Path("/nonexistent/example.json")
        try:
            s = session([EXAMPLE, "0"])
        finally:
            guided.DEMO_FILE = original
        self.assertIn("Couldn't load the example", s.text)
        s.close()


class TestRegressions(unittest.TestCase):
    """Bugs found while auditing. Each of these crashed the program before."""

    def test_exact_name_beats_case_insensitive_match(self):
        # ids that differ only by case can arrive from a JSON file
        g = DependencyGraph()
        g.add_task(Task("A", 1, date(2026, 11, 1)))
        g.add_task(Task("a", 2, date(2026, 11, 2)))
        app = Session([], graph=g).app
        self.assertEqual(app._resolve("a"), "a")
        self.assertEqual(app._resolve("A"), "A")

    def example(self):
        g = DependencyGraph()
        load_file(g, ROOT / "examples" / "tasks.json")
        return g

    def test_far_away_date_is_reasked_not_a_crash(self):
        s = session(["1", "X", "3", "in 3000000 days", "in 99999999999999999999 days",
                     "tomorrow", "1", "0", "n"])
        self.assertEqual(s.text.count("too far away"), 2)
        self.assertIn("X", s.graph.tasks)
        s.close()

    def test_odd_digit_characters_when_picking_do_not_crash(self):
        for token in ("\u00b2", "9" * 5000, "\u0663", "\uff11"):
            for menu_answers in (["6", token, "n", "0"],          # remove task
                                 ["7", token, "1", "0", "n"],     # remove link
                                 ["5", token, "1", "0"]):         # add link
                s = session(menu_answers, graph=self.example())
                self.assertIn("Goodbye", s.text, (menu_answers, token[:10]))
                self.assertEqual(len(s.graph.tasks), 5)
                s.close()

    def test_leap_day_accepted_in_the_menu(self):
        s = session(["1", "Leap", "3", "29 feb", "1", "0", "n"])
        self.assertEqual(s.graph.tasks["Leap"].deadline, date(2028, 2, 29))
        s.close()

    def test_arrows_fall_back_to_ascii_on_limited_consoles(self):
        import io
        import scheduler.guided as guided
        old = sys.stdout
        sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        try:
            self.assertEqual(guided.arrow(), "->")
        finally:
            sys.stdout = old
        sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        try:
            self.assertEqual(guided.arrow(), "\u2192")
        finally:
            sys.stdout = old

    def test_chain_cycle_and_loop_messages_use_the_fallback_arrow(self):
        import io
        old = sys.stdout
        sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        try:
            s = session(["4", "0"], graph=self.example())
            loop = session([LINK, "2", "1", "0"], graph=self.example())
            cyc = DependencyGraph()
            load_file(cyc, ROOT / "examples" / "cycle.json")
            c = session(["3", "0"], graph=cyc)
        finally:
            sys.stdout = old
        self.assertIn("build -> test -> deploy", s.text)
        self.assertNotIn("\u2192", s.text + loop.text + c.text)
        self.assertIn("b -> c -> a -> b", c.text)
        for x in (s, loop, c):
            x.close()


class TestRealProcess(unittest.TestCase):
    def run_main(self, args, stdin):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, str(ROOT / "main.py"), *args], input=stdin,
                               capture_output=True, text=True, cwd=d, timeout=30)
            return r, sorted(os.listdir(d))

    def test_guided_is_the_default(self):
        r, files = self.run_main([], f"{EXAMPLE}\n{PLAN}\n0\n")
        self.assertEqual(r.returncode, 0)
        self.assertIn("What would you like to do?", r.stdout)
        self.assertIn("Your plan", r.stdout)
        self.assertEqual(files, [])

    def test_demo_flag_goes_straight_to_the_menu_with_tasks(self):
        r, _ = self.run_main(["--demo"], f"{LIST}\n0\n")
        self.assertIn("Your tasks (5)", r.stdout)

    def test_does_not_overwrite_loaded_file_when_saving(self):
        r, files = self.run_main(["--file", str(ROOT / "examples" / "tasks.json")], f"{SAVE}\n0\n")
        self.assertIn("Saved 5 tasks to my_tasks.json", r.stdout)
        self.assertEqual(files, ["my_tasks.json"])

    def run_env(self, args, stdin_bytes, env_extra):
        env = dict(os.environ, **env_extra)
        with tempfile.TemporaryDirectory() as d:
            return subprocess.run([sys.executable, str(ROOT / "main.py"), *args],
                                  input=stdin_bytes, capture_output=True, cwd=d, env=env, timeout=30)

    def test_ascii_only_console_does_not_crash_on_arrows_or_other_scripts(self):
        # Hindi task name typed in, arrows printed out, on a console that can show neither
        typed = "1\n\u0930\u093f\u092a\u094b\u0930\u094d\u091f\n3\ntomorrow\n1\n"      # add the Hindi-named task
        typed += "1\nB\n3\ntomorrow\n1\n1\n"                                              # add B, which waits for it
        typed += "4\n0\nn\n"                                                             # longest chain, then quit
        r = self.run_env([], typed.encode("utf-8"), {"PYTHONIOENCODING": "ascii"})
        self.assertEqual(r.returncode, 0, r.stderr.decode(errors="replace")[-300:])
        out = r.stdout.decode("ascii", errors="replace")
        self.assertIn("->", out)
        self.assertNotIn("Traceback", r.stderr.decode(errors="replace"))

    def test_undecodable_input_bytes_do_not_crash(self):
        r = self.run_env([], b"1\n\xff\xfe\x81name\n3\ntomorrow\n1\n0\nn\n", {"PYTHONIOENCODING": "ascii"})
        self.assertEqual(r.returncode, 0, r.stderr.decode(errors="replace")[-300:])

    def test_typed_mode_ctrl_c_exits_cleanly(self):
        import signal
        with tempfile.TemporaryDirectory() as d:
            p = subprocess.Popen([sys.executable, str(ROOT / "main.py"), "--commands"],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, cwd=d)
            p.stdout.readline()                      # wait until it is waiting for input
            p.send_signal(signal.SIGINT)
            out, err = p.communicate(timeout=15)
        self.assertEqual(p.returncode, 0)
        self.assertNotIn(b"Traceback", err)

    def test_closing_the_output_early_is_quiet(self):
        many = f"{EXAMPLE}\n" + f"{PLAN}\n" * 400 + "0\n"       # far more output than a pipe can hold
        with tempfile.TemporaryDirectory() as d:
            p = subprocess.Popen([sys.executable, str(ROOT / "main.py")], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=d)
            p.stdin.write(many.encode())
            p.stdin.close()
            p.stdout.readline()
            p.stdout.close()                         # like `| head -1`
            err = p.stderr.read()
            p.stderr.close()
            p.wait(timeout=15)
        self.assertNotIn(b"Traceback", err)
        self.assertNotIn(b"BrokenPipeError", err)

    def test_empty_input_exits_cleanly(self):
        r, _ = self.run_main([], "")
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)

    def test_commands_flag_keeps_the_old_mode(self):
        r, _ = self.run_main(["--commands"], "help\nquit\n")
        self.assertIn("typed commands", r.stdout)
        self.assertIn("depend <task> <needs>", r.stdout)


if __name__ == "__main__":
    unittest.main()
