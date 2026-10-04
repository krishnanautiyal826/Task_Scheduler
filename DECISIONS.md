# Design Decisions

## 1. Kahn's algorithm with a heap, instead of DFS

**Options considered:** a DFS-based topological sort, or Kahn's algorithm.

**Chosen:** Kahn's algorithm, with a min-heap holding the tasks that are ready to run.

**Why:**
- The task needs ordering by priority and deadline, not just any valid order. In Kahn's algorithm the set of ready tasks is explicit, so replacing the plain queue with a heap gives a priority-aware order directly. A DFS finishing order does not offer a natural place to apply that preference.
- Cycle detection comes with the algorithm. Tasks in a cycle never reach in-degree 0, so they never leave the waiting state. No second pass is needed.

## 2. Silent failure on cycles, found and fixed

The first version of `schedule()` returned whatever order it could build. When two tasks depended on each other it returned an empty list with no error, which looks like a valid result.

**Change:** after the loop, if the order is shorter than the number of tasks, `schedule()` raises `CycleError`. The error carries the cycle and the list of tasks blocked behind it.

**Edge case this exposed:** the leftover tasks are not all part of the cycle. A task that merely depends on a cyclic task is stuck too. Reporting every leftover task as circular would be wrong, so the cycle is extracted by walking backwards through unfinished prerequisites until a task repeats, and everything else is reported as blocked.

## 3. Cycles are checked when scheduling, not when adding a dependency

Rejecting a cycle at insertion time would cost O(V + E) per `add_dependency`. Checking once, inside `schedule()`, costs nothing extra because Kahn's algorithm already reveals the cycle. The trade-off is that a cyclic graph can be built and only fails when scheduled, so the CLI reports the error at `schedule` time.

## 4. Sets for adjacency, immutable tasks

- Dependencies are stored in sets so a repeated `depend` command cannot inflate a task's in-degree. With lists, a duplicate edge would leave the task waiting forever and make it look cyclic.
- `Task` is a frozen dataclass so a task cannot change while it sits in the heap.
- `schedule()` works on a copy of the in-degrees and never modifies the graph, so it can be called repeatedly. A test confirms this.

## 5. Deterministic ordering

The heap key is `(deadline, -priority, id)`. Without the final id, tasks tied on deadline and priority could come out in set-iteration order, which makes tests unreliable.

## 6. Scope

Deadlines influence ordering but are not enforced. Durations are used only by critical-path analysis and do not affect the order. A scheduler that guarantees deadlines would need to model workers and durations together, which is a harder problem. The task asks for a valid order that respects dependencies and priority, so the greedy approach was kept and the limitation is stated in the README.

## 7. Critical path as an optional extension

**What it needed:** task durations, which the model did not have.

**Decision:** add `duration` to `Task` as an optional field that defaults to 1 day. Existing tasks, JSON files and tests keep working unchanged, and the core scheduler does not depend on it.

**Method:** a dynamic-programming pass over the topological order already produced by `schedule()`. A task's earliest finish is its duration plus the latest finish among its prerequisites. Reusing `schedule()` means a cycle raises the same `CycleError` and no second cycle check is needed. Ties are broken by the smaller id for deterministic output.

**Trade-off:** the critical path assumes unlimited parallel workers, while `schedule()` prints one sequence. The two answer different questions, so the README states the difference and does not present the critical-path length as the length of the printed schedule.

## 8. Strict input parsing

Dates must be written `YYYY-MM-DD` and numbers must be whole numbers. Python's own `date.fromisoformat` accepts more formats on newer versions (for example `20261101`), so the same input could work on one machine and fail on another. A regular expression check in front of it keeps behaviour identical across versions. The same parsing is used for typed commands and JSON files, and every failure produces a plain message that names the field, not a Python error.

Loading a JSON file validates its structure first (a `tasks` list, required keys, dependency pairs) so a malformed file exits with a clear message instead of a traceback. The `demo` command only loads into an empty scheduler, which avoids a half-loaded state when ids collide.

## 9. A guided menu as the default interface

**What was wrong.** Running the first version as a new user showed several problems: a blank prompt with no hint of what to type; `add` rejected names with spaces and printed a usage line; `tomorrow` or `3/11/2026` were rejected; `depend a b` did not say which task waits for which; the plan never explained why a task with an early due date was listed last; nothing was saved; and a typo could not be undone.

**Decision.** `python main.py` now opens a menu that asks one plain question at a time, shows what a sensible answer looks like, repeats back how it understood a date, and lets the user type `cancel` at any point. The old typed commands remain behind `--commands`.

**Why keep both.** The typed mode is quick for repeated use and the existing tests exercise it. The cost is two interfaces to maintain. They share the same core (`DependencyGraph`, `schedule`, `critical_path`), so only the input and output layer is duplicated.

**What changed in the core.** `DependencyGraph` gained `remove_task`, `remove_dependency` and `find_path`. The scheduling algorithms are unchanged.

**Explaining the plan.** The plan shows what each task waits for, prints the rule used to order tasks, and adds a heads-up when a task is due earlier than something it waits for. That warning only compares the dates of directly linked tasks; it does not prove a deadline will be missed.

## 10. Loop checks at entry in the menu, not in the core

Decision 3 kept cycle detection out of `add_dependency` to avoid an O(V + E) cost on every insert. That is still true for the core, and `schedule()` still detects loops. The menu, however, checks before adding a link (using `find_path`) and refuses one that would create a loop. For a person typing one link at a time the cost is irrelevant, and an immediate "that would create a loop: A → B → A" is much clearer than a failure later. A new task added with its waits-for list cannot create a loop, because nothing can yet wait for it, so no check is needed there. Loops can still arrive through a loaded file, and the plan then explains them in plain words.

## 11. Friendly dates only in the menu

Decision 8 made date parsing strict so a command behaves the same on every Python version. The menu accepts natural dates, but through its own parser (`dates.py`) written with explicit rules rather than relying on Python's version-dependent parsing. Two choices to be aware of: dates are read **day first** (`05/11/2026` is 5 November), and a date with no year means its next occurrence (`2 oct` typed on 3 October means next year). The menu always repeats the parsed date back, and flags a date that has already passed, so a misread is visible immediately. JSON files and typed commands stay strict `YYYY-MM-DD`.

## 12. Saving

Saving is explicit (the Save menu option) and offered on quit. The menu always writes to `my_tasks.json` in the current folder and never to a file opened with `--file`, so the example data cannot be overwritten by accident. Writes go to a temporary file that is then renamed into place, so a crash during saving cannot leave a half-written file. The cost is that tasks entered but not saved are lost if the program is killed.

Saving also refuses to replace a saved list the session never loaded without asking. This was found by testing, not planned: declining "Load saved tasks?", adding one task, and saving overwrote a five-task file with no warning. The menu now tracks whether the current list came from, or has been saved to, the file. If not, and the file holds different tasks, it asks first with the answer defaulting to no, and a refused replacement leaves the file and the list untouched. An unreadable existing file is treated the same way. A file holding no tasks, or the same tasks, is replaced without a question.

## 13. Changing a task

**What was missing.** The only way to fix a typo was to remove the task and add it again, which also dropped every link to it.

**Decision.** One flow, "Change a task", that asks the same questions as adding a task but shows the current value as the default, so Enter keeps it. Importance, due date and days reuse the exact same question code as "add", so a change cannot accept something an add would refuse.

**Atomic.** Every answer is validated while asking, and nothing is applied until the last one. Cancelling part-way, or a refused link, leaves the task exactly as it was. This matters because a rename plus link changes touch several parts of the graph.

**Core support.** `DependencyGraph.replace_task` changes a task's details and optionally renames it. A rename rewrites both adjacency maps and the task list, so every link follows the new name and the task keeps its position. Tasks stay immutable (decision 4); the dictionary entry is replaced, not the object edited. Renaming costs O(V + E) because the maps are rebuilt; changing details only is O(1).

**Loops.** When the "waits for" list is edited, each new prerequisite is checked with `find_path` (decision 10) before anything is applied, and a link that would create a loop is refused with the chain shown. Prerequisites that stay unchanged are not rechecked.

**Typed mode.** `edit <task> <field> <value>` covers name, priority, deadline and days. It deliberately does not edit the waits-for list: one line cannot express a list cleanly, and the menu does it with confirmation of loops. This leaves typed mode able to add links (`depend`) but not remove them, which is a known gap.

## 14. Menu numbers come from one list

Adding "Change a task" meant renumbering the menu. The numbers had been written by hand in six places in the program text (hints such as "choose 8 to load an example") and in about 25 test lines. The menu, its numbers, the help text and every hint are now generated from a single ordered list in `guided.py`, and the tests refer to items by name. Inserting an item can no longer leave a stale number behind. The cost is that the numbers are not stable across versions, so `USAGE.md` is also generated from that list.

## 15. Robustness fixes found by auditing

A deliberate bug hunt (probing odd inputs, random testing of every parser and of the menu, a lint pass, and running under restricted console settings) found problems the normal tests had not. All are fixed and each has a regression test:

- A date far in the future (`in 99999999999 days`) crashed with a raw `OverflowError`.
- `29 feb` with no year failed in a non-leap year instead of finding the next leap day.
- Characters such as `²`, and very long digit strings, crashed the "pick from a list" questions because `str.isdigit()` accepts more than `int()` does. Only plain ASCII digits are now treated as numbers.
- The same non-ASCII digits were accepted as dates, so `٥/١١/٢٠٢٦` was read as 5 November. Dates now use ASCII digits only.
- Numbers inside a JSON file were not bounded, and a deeply nested file crashed with `RecursionError`.
- Pressing Ctrl-C at the typed-command prompt, or closing the output early (`| head`), printed a traceback.
- On consoles that cannot show `→`, or cannot read non-ASCII input, the program crashed. It now falls back to `->` and replaces unusable characters instead of failing.
- A saved file was created readable only by its owner, unlike a normal file.
- A task whose name contains a comma (possible from a JSON file) could not be picked by name.
- The silent overwrite described in decision 12.

