"""Guided, menu-driven interface: asks plain questions instead of needing syntax."""
import re
import sys
from datetime import date
from pathlib import Path

from .critical_path import critical_path
from .dates import fmt_date, parse_friendly_date, parse_importance
from .graph import DependencyGraph
from .scheduler import CycleError, schedule
from .storage import DEMO_FILE, graph_to_data, load_file, parse_int, save_file
from .task import Task

BANNER = ("\nTask Scheduler\n"
          "Put your tasks in the right order, with the things they depend on first.\n"
          "Type ? at the menu for help. Type 'cancel' at any question to stop.")

# (key, text), in the order shown. Numbers are assigned from this order, so adding an
# item can never leave a stale number in a hint, the help text or the menu.
ITEMS = [
    ("add", "Add a task"),
    ("list", "See my tasks"),
    ("plan", "Get my plan (what to do, in what order)"),
    ("chain", "Find what could delay everything"),
    ("change", "Change a task"),
    ("link", "Say that one task must wait for another"),
    ("remove_task", "Remove a task"),
    ("remove_link", 'Remove a "must wait for" link'),
    ("example", "Load an example"),
    ("save", "Save my tasks"),
]
NUM = {key: str(i) for i, (key, _) in enumerate(ITEMS, 1)}
MENU = ("\nWhat would you like to do?\n"
        + "\n".join(f"  {NUM[key]:<2} {text}" for key, text in ITEMS)
        + "\n  0  Quit")

HELP_TEXT = f"""
How this works
  A task has a name, an importance (1 = low ... 5 = urgent), a due date and
  how many days it takes.
  "Waits for" means a task cannot start until another one is finished.
  Example: "Deploy" waits for "Test".
  The plan puts every task after the ones it waits for. When several tasks are
  ready at once, the one due soonest goes first, then the more important one.
  Made a mistake? Use {NUM["change"]} to fix a task, or {NUM["remove_task"]} / {NUM["remove_link"]} to remove a task or a link."""

EMPTY_HINT = (f"You have no tasks yet. Choose {NUM['add']} to add one, "
              f"or {NUM['example']} to load an example.")


class _Cancelled(Exception):
    pass


def arrow() -> str:
    """'→' where the console can show it, '->' where it cannot (some Windows consoles)."""
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        "→".encode(encoding)
        return "→"
    except (UnicodeEncodeError, LookupError):
        return "->"


def is_number(token: str) -> bool:
    """Plain ASCII digits only, and short. (str.isdigit() also accepts characters like
    '²' that int() rejects, and very long digit strings that int() refuses.)"""
    return re.fullmatch(r"[0-9]{1,9}", token) is not None


class GuidedApp:
    def __init__(self, graph=None, ask=input, say=print, today=date.today,
                 data_path="my_tasks.json"):
        self.graph = graph if graph is not None else DependencyGraph()
        self.ask, self.say, self.today = ask, say, today
        self.data_path = data_path
        self.dirty = False          # unsaved changes?
        self.owns_file = False      # True once the list came from, or was saved to, data_path
        self.actions = {NUM["add"]: self.add_task, NUM["list"]: self.show_tasks,
                        NUM["plan"]: self.show_plan, NUM["chain"]: self.show_longest_chain,
                        NUM["change"]: self.change_task, NUM["link"]: self.add_link,
                        NUM["remove_task"]: self.remove_task, NUM["remove_link"]: self.remove_link,
                        NUM["example"]: self.load_example, NUM["save"]: self.save}

    # ---------- input helpers ----------
    def _prompt(self, text, cancellable=True):
        answer = self.ask(text).strip()
        if cancellable and answer.lower() in ("cancel", "back"):
            raise _Cancelled
        return answer

    def _yes_no(self, text, default):
        hint = "Y/n" if default else "y/N"
        while True:
            a = self._prompt(f"{text} ({hint}): ", cancellable=False).lower()
            if not a:
                return default
            if a in ("y", "yes"):
                return True
            if a in ("n", "no"):
                return False
            self.say("Please answer y or n.")

    def _names(self):
        return list(self.graph.tasks)

    def _resolve(self, token):
        """A list number or a task name (any capitalisation) -> task name, else None."""
        token = token.strip()
        names = self._names()
        if is_number(token):
            i = int(token)
            return names[i - 1] if 1 <= i <= len(names) else None
        if token in names:                    # an exact match always wins
            return token
        for n in names:
            if n.lower() == token.lower():
                return n
        return None

    def _show_numbered(self):
        for i, n in enumerate(self._names(), 1):
            self.say(f"  {i}. {n}")

    def _choose_one(self, prompt):
        while True:
            text = self._prompt(prompt)
            if not text:
                self.say("Please type a number or a name from the list.")
                continue
            found = self._resolve(text)
            if found:
                return found
            self.say(f"I don't see '{text}' in the list. Type its number or its name.")

    def _parse_many(self, text):
        """Comma-separated numbers/names -> (picked names, unknown pieces).

        If the whole text is one task's name, that wins, so a task called
        'Send, final' can still be picked by typing its name."""
        whole = self._resolve(text)
        if whole is not None:
            return [whole], []
        picked, unknown = [], []
        for token in text.split(","):
            if not token.strip():
                continue
            found = self._resolve(token)
            if found is None:
                unknown.append(token.strip())
            elif found not in picked:
                picked.append(found)
        return picked, unknown

    def _choose_many(self, prompt):
        """Comma-separated numbers/names. Empty answer means none."""
        while True:
            text = self._prompt(prompt)
            if not text:
                return []
            picked, unknown = self._parse_many(text)
            if unknown:
                self.say("I don't see: " + ", ".join(unknown) + ". Use numbers or names from the list.")
                continue
            return picked

    def _describe(self, t):
        days = f"{t.duration} day" + ("" if t.duration == 1 else "s")
        return f"due {fmt_date(t.deadline)}, importance {t.priority}/5, {days}"

    # ---------- main loop ----------
    def run(self, offer_saved=True):
        self.say(BANNER)
        try:
            if offer_saved:
                self.offer_saved_tasks()
            while True:
                self.say(MENU)
                choice = self._prompt("Your choice: ", cancellable=False).lower()
                if choice in ("0", "q", "quit", "exit"):
                    if self.quit():
                        return
                elif choice in ("?", "h", "help"):
                    self.say(HELP_TEXT)
                elif choice in self.actions:
                    try:
                        self.actions[choice]()
                    except _Cancelled:
                        self.say("Cancelled. Nothing was changed.")
                else:
                    self.say(f"Please type a number from the menu (for example {NUM['add']} to add a task).")
        except (EOFError, KeyboardInterrupt):
            self.say("")
            self.say("Goodbye. Your latest changes were not saved." if self.dirty else "Goodbye.")

    def quit(self):
        if self.dirty:
            if self._yes_no(f"You have unsaved changes. Save them to {self.data_path} first?", True):
                if not self.save() and not self._yes_no("Quit anyway?", False):
                    return False
        self.say("Goodbye.")
        return True

    # ---------- actions ----------
    def offer_saved_tasks(self):
        if self.graph.tasks or not Path(self.data_path).exists():
            return
        fresh = DependencyGraph()
        try:
            load_file(fresh, self.data_path)
        except (OSError, ValueError) as e:
            self.say(f"\nI found {self.data_path} but couldn't read it ({e}). Starting empty.")
            return
        if not fresh.tasks:
            return
        n = len(fresh.tasks)
        if self._yes_no(f"\nFound {n} saved task{'s' if n != 1 else ''} in {self.data_path}. Load them?", True):
            self.graph = fresh
            self.owns_file = True
            self.say(f"Loaded {n} task{'s' if n != 1 else ''}.")

    # ---------- the questions, shared by "add" and "change" ----------
    def _ask_name(self, current=None):
        """With `current` (changing a task) Enter keeps it, and a change of letter case is allowed."""
        others = [n.lower() for n in self._names() if n != current]
        hint = f" [{current}]" if current else ""
        while True:
            name = self._prompt(f"What is the task called?{hint} ")
            if not name:
                if current:
                    return current
                self.say("A task needs a name.")
            elif "," in name:
                self.say("Please leave out commas in the name.")
            elif is_number(name):
                self.say("Please include a word in the name (numbers alone are used to pick from lists).")
            elif name.lower() in others:
                self.say(f"You already have a task called '{name}'. Choose another name.")
            else:
                return name

    def _ask_importance(self, default=3):
        while True:
            text = self._prompt(f"How important is it? 1 = low ... 5 = urgent [{default}]: ")
            if not text:
                return default
            try:
                return parse_importance(text)
            except ValueError as e:
                self.say(str(e))

    def _ask_due(self, default=None):
        hint = f" [{fmt_date(default)}]" if default else ""
        while True:
            text = self._prompt(f"When is it due? (tomorrow, friday, 5 nov, 05/11/2026){hint}: ")
            if not text:
                if default:
                    return default
                self.say("A due date is needed.")
                continue
            try:
                due = parse_friendly_date(text, self.today())
            except ValueError as e:
                self.say(str(e))
                continue
            note = "  (that date has already passed)" if due < self.today() else ""
            self.say(f"Due date: {fmt_date(due)}{note}")
            return due

    def _ask_days(self, default=1):
        while True:
            text = self._prompt(f"How many days will it take? [{default}]: ")
            if not text:
                return default
            try:
                days = parse_int("days", text)
            except ValueError:
                self.say("Please type a whole number of days, like 1 or 3.")
                continue
            if days < 1:
                self.say("It needs to take at least 1 day.")
                continue
            return days

    # ---------- actions ----------
    def add_task(self):
        self.say("\nLet's add a task.")
        name = self._ask_name()
        importance = self._ask_importance(3)
        due = self._ask_due()
        days = self._ask_days(1)
        blockers = []
        if self.graph.tasks:
            self.say("\nYour other tasks:")
            self._show_numbered()
            blockers = self._choose_many(
                "Does it have to wait for any of these? Numbers or names, separated by commas (Enter for none): ")
        self.graph.add_task(Task(name, importance, due, days))
        for b in blockers:        # a brand-new task can't be waited on yet, so no loop is possible
            self.graph.add_dependency(name, b)
        self.dirty = True
        tail = f" Waits for: {', '.join(blockers)}." if blockers else ""
        self.say(f"Added '{name}': {self._describe(self.graph.tasks[name])}.{tail}")

    def _waits_for_problem(self, name, picked):
        """Why `name` cannot wait for all of `picked`, or None if it can."""
        for b in picked:
            if b == name:
                return "A task can't wait for itself."
            loop = self.graph.find_path(name, b)
            if loop:
                return (f"'{name}' can't wait for '{b}': '{b}' already has to wait for '{name}' "
                        f"({f' {arrow()} '.join(loop)}), so they would wait on each other.")
        return None

    def _ask_waits_for(self, name, current):
        shown = ", ".join(current) if current else "nothing"
        self.say("\nYour tasks:")
        for i, n in enumerate(self._names(), 1):
            self.say(f"  {i}. {n}" + ("   (this task)" if n == name else ""))
        while True:
            text = self._prompt(f"What does it wait for? Right now: {shown}.\n"
                                "Numbers or names separated by commas, 'none' for nothing, Enter to keep: ")
            if not text:
                return list(current)
            if text.lower() in ("none", "nothing") and self._resolve(text) is None:
                return []
            picked, unknown = self._parse_many(text)
            if unknown:
                self.say("I don't see: " + ", ".join(unknown) + ". Use numbers or names from the list.")
                continue
            problem = self._waits_for_problem(name, picked)
            if problem:
                self.say(problem)
                continue
            return picked

    def change_task(self):
        if not self.graph.tasks:
            self.say("\n" + EMPTY_HINT)
            return
        self.say("\nYour tasks:")
        self._show_numbered()
        name = self._choose_one("Which task do you want to change? (number or name): ")
        old = self.graph.tasks[name]
        waits = sorted(self.graph.prerequisites[name])
        self.say(f"\nChanging '{name}': {self._describe(old)}.")
        self.say("Press Enter at any question to keep what it is now.")
        new_name = self._ask_name(current=name)
        importance = self._ask_importance(old.priority)
        due = self._ask_due(old.deadline)
        days = self._ask_days(old.duration)
        new_waits = self._ask_waits_for(name, waits) if len(self.graph.tasks) > 1 else waits

        a = arrow()
        changes = []
        if new_name != name:
            changes.append(f"name: {name} {a} {new_name}")
        if importance != old.priority:
            changes.append(f"importance: {old.priority} {a} {importance}")
        if due != old.deadline:
            changes.append(f"due: {fmt_date(old.deadline)} {a} {fmt_date(due)}")
        if days != old.duration:
            changes.append(f"days: {old.duration} {a} {days}")
        if set(new_waits) != set(waits):
            changes.append(f"waits for: {', '.join(waits) or 'nothing'} {a} "
                           f"{', '.join(sorted(new_waits)) or 'nothing'}")
        if not changes:
            self.say("Nothing was changed.")
            return
        # everything was checked while asking, so applying cannot fail halfway
        self.graph.replace_task(name, Task(new_name, importance, due, days))
        for gone in set(waits) - set(new_waits):
            self.graph.remove_dependency(new_name, gone)
        for added in set(new_waits) - set(waits):
            self.graph.add_dependency(new_name, added)
        self.dirty = True
        self.say(f"Changed '{new_name}':")
        for line in changes:
            self.say(f"  - {line}")

    def show_tasks(self):
        if not self.graph.tasks:
            self.say("\n" + EMPTY_HINT)
            return
        self.say(f"\nYour tasks ({len(self.graph.tasks)}):")
        for i, (name, t) in enumerate(self.graph.tasks.items(), 1):
            self.say(f"{i}. {name}\n   {self._describe(t)}")
            waits = sorted(self.graph.prerequisites[name])
            if waits:
                self.say(f"   waits for: {', '.join(waits)}")

    def _explain_cycle(self, e):
        self.say("\nSome tasks are waiting on each other, so none of them can go first:")
        self.say("  " + f" {arrow()} ".join(e.cycle) + "   (each task must be done before the next)")
        if e.blocked:
            self.say("Also stuck because of that: " + ", ".join(e.blocked))
        self.say(f"Fix it by removing one link (menu option {NUM['remove_link']}).")

    def show_plan(self):
        if not self.graph.tasks:
            self.say("\n" + EMPTY_HINT)
            return
        try:
            order = schedule(self.graph)
        except CycleError as e:
            self._explain_cycle(e)
            return
        self.say(f"\nYour plan: {len(order)} task{'s' if len(order) != 1 else ''}, in the order to do them\n")
        for i, t in enumerate(order, 1):
            self.say(f"{i}. {t.id}\n   {self._describe(t)}")
            waits = sorted(self.graph.prerequisites[t.id])
            if waits:
                self.say(f"   after: {', '.join(waits)}")
        warnings = [(t, p) for t in order for p in sorted(self.graph.prerequisites[t.id])
                    if self.graph.tasks[p].deadline > t.deadline]
        for t, p in warnings:
            self.say(f"\nHeads-up: '{p}' must be finished before '{t.id}' can start, but "
                     f"'{p}' is due {fmt_date(self.graph.tasks[p].deadline)}, later than "
                     f"'{t.id}' ({fmt_date(t.deadline)}). One of those dates probably needs to change.")
        self.say("\nHow the order is chosen: a task goes only after everything it waits for is done. "
                 "When several are ready, the one due soonest goes first, then the more important one.")

    def show_longest_chain(self):
        if not self.graph.tasks:
            self.say("\n" + EMPTY_HINT)
            return
        try:
            path, total = critical_path(self.graph)
        except CycleError as e:
            self._explain_cycle(e)
            return
        alone = sum(t.duration for t in self.graph.tasks.values())
        self.say(f"\nLongest chain: {f' {arrow()} '.join(t.id for t in path)}  ({total} day{'s' if total != 1 else ''})")
        self.say("If any task on this chain slips, everything finishes later.")
        self.say(f"That total assumes tasks that don't depend on each other happen at the same time. "
                 f"Doing one thing at a time, everything takes {alone} day{'s' if alone != 1 else ''}.")

    def add_link(self):
        if len(self.graph.tasks) < 2:
            self.say("\nYou need at least two tasks to link them.")
            return
        self.say("\nYour tasks:")
        self._show_numbered()
        blocked = self._choose_one("Which task has to wait? (number or name): ")
        while True:
            needs = self._choose_one(f"What must be finished before '{blocked}' can start? (number or name): ")
            if needs == blocked:
                self.say("A task can't wait for itself.")
                continue
            break
        if needs in self.graph.prerequisites[blocked]:
            self.say(f"'{blocked}' already waits for '{needs}'.")
            return
        loop = self.graph.find_path(blocked, needs)
        if loop:
            self.say(f"That would create a loop: {f' {arrow()} '.join(loop + [blocked])}\n"
                     f"('{needs}' already has to wait for '{blocked}', so they'd wait on each other.) Nothing was changed.")
            return
        self.graph.add_dependency(blocked, needs)
        self.dirty = True
        self.say(f"Done. '{blocked}' now waits for '{needs}'.")

    def remove_task(self):
        if not self.graph.tasks:
            self.say("\nThere are no tasks to remove.")
            return
        self.say("\nYour tasks:")
        self._show_numbered()
        name = self._choose_one("Which task do you want to remove? (number or name): ")
        freed = sorted(self.graph.dependents[name])
        extra = f" {', '.join(freed)} will no longer wait for it." if freed else ""
        if not self._yes_no(f"Remove '{name}'?{extra}", False):
            self.say("Okay, nothing was removed.")
            return
        self.graph.remove_task(name)
        self.dirty = True
        self.say(f"Removed '{name}'.")

    def remove_link(self):
        links = sorted((t, n) for t, needs in self.graph.prerequisites.items() for n in needs)
        if not links:
            self.say("\nNo task is waiting for another yet, so there's nothing to remove.")
            return
        self.say("\nCurrent links:")
        for i, (t, n) in enumerate(links, 1):
            self.say(f"  {i}. '{t}' waits for '{n}'")
        while True:
            text = self._prompt("Which link do you want to remove? (number): ")
            if is_number(text) and 1 <= int(text) <= len(links):
                t, n = links[int(text) - 1]
                break
            self.say(f"Please type a number from 1 to {len(links)}.")
        self.graph.remove_dependency(t, n)
        self.dirty = True
        self.say(f"Removed. '{t}' no longer waits for '{n}'.")

    def load_example(self):
        if self.graph.tasks:
            self.say("\nThe example only loads into an empty list, so it can't overwrite your tasks. "
                     "Remove your tasks first, or restart the program.")
            return
        try:
            load_file(self.graph, DEMO_FILE)
        except (OSError, ValueError) as e:
            self.say(f"Couldn't load the example: {e}")
            return
        self.say(f"\nLoaded an example with 5 tasks. Try option {NUM['plan']} to see the plan.")

    def _confirm_replacing_other_file(self):
        """Saving would replace a file this session never loaded: say so first."""
        if self.owns_file or not Path(self.data_path).exists():
            return True
        other = DependencyGraph()
        try:
            load_file(other, self.data_path)
        except (OSError, ValueError):
            return self._yes_no(f"{self.data_path} already exists and can't be read as a task list. "
                                f"Replace it?", False)
        if graph_to_data(other) == graph_to_data(self.graph):
            return True                      # same content: nothing is lost
        n = len(other.tasks)
        if n == 0:
            return True
        return self._yes_no(f"{self.data_path} already holds {n} saved task{'s' if n != 1 else ''} "
                            f"that are not in your current list. Replace them?", False)

    def save(self):
        if not self._confirm_replacing_other_file():
            self.say("Okay, nothing was saved. Your tasks are still here.")
            return False
        try:
            save_file(self.graph, self.data_path)
        except OSError as e:
            self.say(f"Couldn't save: {e}")
            return False
        self.owns_file = True
        self.dirty = False
        n = len(self.graph.tasks)
        self.say(f"Saved {n} task{'s' if n != 1 else ''} to {self.data_path}.")
        return True
