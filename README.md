# Task Scheduler

A task scheduler for the terminal that orders tasks so every dependency is finished before the task that needs it. When several tasks are ready, it picks the one with the earliest deadline, then the highest priority. If tasks depend on each other in a loop, it reports the loop instead of returning a wrong answer.

## Features

- A guided menu that asks plain questions (no commands to learn); see [USAGE.md](USAGE.md)
- Create tasks with an importance (1 to 5), a due date, and an optional duration in days
- Dates can be typed naturally: `tomorrow`, `friday`, `5 nov`, `05/11/2026` (day first)
- Declare that one task depends on another; a link that would create a loop is refused
- Produce a valid completion order that respects dependencies and priority, with the reasoning shown
- Warn when two dates contradict each other (a task due before something it waits for)
- Detect circular dependencies and name the tasks in the loop
- Find the critical path: the longest chain of dependent tasks
- Change a task (name, importance, due date, days, what it waits for) without losing its links, and remove tasks and links
- Save and reload tasks as JSON; saving never silently replaces a saved list you chose not to load
- A typed-command mode for people who prefer it (`--commands`)

## Requirements

Python 3.9 or newer. No packages to install. The test suite was run on Python 3.11, 3.12 and 3.13; 3.9 and 3.10 were not available to run, but a static check says 3.9 is the minimum.

## Run

```bash
python main.py                          # guided menu (recommended)
python main.py --demo                   # guided menu, example tasks already loaded
python main.py --file examples/tasks.json
python main.py --commands               # typed commands instead of the menu
```

The guided menu is explained step by step, with a real example session, in **[USAGE.md](USAGE.md)**.

### Typed commands (`--commands`)

| Command | Meaning |
|---|---|
| `add <id> <priority 1-5> <YYYY-MM-DD> [days]` | create a task (`days` defaults to 1) |
| `depend <task> <needs>` | `<task>` cannot start until `<needs>` is done |
| `list` | show all tasks and their dependencies |
| `schedule` | print a valid completion order |
| `critical` | print the critical path and its total length |
| `edit <task> <field> <value>` | change `name`, `priority`, `deadline` or `days` of a task |
| `demo` | load the example from `examples/tasks.json` (only into an empty scheduler) |
| `help`, `quit` | |

### Example (typed-command mode)

Using `examples/tasks.json`, where `deploy` needs `test` and `test` needs `build`:

```
> schedule
1. lint  (due 2026-11-02, priority 5)
2. docs  (due 2026-11-02, priority 2)
3. build  (due 2026-11-05, priority 3)
4. test  (due 2026-11-06, priority 4)
5. deploy  (due 2026-11-01, priority 5)
```

`deploy` has the earliest deadline but runs last, because it cannot start until `build` and `test` are finished. Dependencies take precedence over deadlines.

The critical path for the same file:

```
> critical
Critical path (6 days): build -> test -> deploy
```

With `examples/cycle.json`:

```
> schedule
Cannot continue. Circular dependency: b -> c -> a -> b
Also blocked by the cycle: d
```

## How it works

### Graph representation

Tasks are nodes in a directed graph. An edge `A -> B` means A must finish before B starts. `DependencyGraph` stores each task's data plus two adjacency maps:

- `dependents[A]`: the tasks waiting on A
- `prerequisites[B]`: the tasks B is waiting on

The number of prerequisites of a task is its in-degree. Both maps use sets, so declaring the same dependency twice has no effect.

### Algorithm

The scheduler uses Kahn's algorithm for topological sorting, with a min-heap in place of the usual queue.

1. Copy each task's in-degree into a working table.
2. Put every task with in-degree 0 (nothing to wait for) into a min-heap.
3. Pop the best ready task, add it to the order, and reduce the in-degree of each task waiting on it.
4. Any task whose in-degree reaches 0 is now ready and is pushed onto the heap.
5. Repeat until the heap is empty.

The heap key is `(deadline, -priority, id)`: earliest deadline first, then higher priority, then id so the result is deterministic.

If the final order contains fewer tasks than the graph, the remaining tasks are waiting on each other. A cycle is then found by walking backwards through unfinished prerequisites until a task repeats. Tasks that are only stuck behind the cycle are reported separately as blocked.

### Critical path

The critical path is the longest chain of dependent tasks, measured by total duration. It is the minimum time needed to finish everything if any number of independent tasks could run at the same time. Any delay to a task on this path delays the whole project.

It is computed in one pass over the order that `schedule()` already produces. For each task, the earliest finish time is its own duration plus the latest finish time among its prerequisites. The path is recovered by walking back from the task that finishes last. Ties are broken by the smaller task id so the result is deterministic.

### Complexity

V is the number of tasks and E is the number of dependencies.

| Operation | Time | Space |
|---|---|---|
| `add_task`, `add_dependency` | O(1) average | |
| `schedule` | O(V log V + E) | O(V + E) |
| Cycle reporting (only on failure) | O(V + E) | O(V) |
| `critical_path` | O(V log V + E) | O(V + E) |
| `find_path` (loop check when linking in the menu) | O(V + E) | O(V) |
| `remove_dependency` | O(1) average | |
| `replace_task` (change a task) | O(1) to change details; O(V + E) if it is renamed | |
| `remove_task` | O(degree of the task) | |

Each task is pushed onto and popped from the heap once (V heap operations of O(log V) each), and each dependency is examined once.

## Project layout

```
scheduler/
  task.py        Task model and validation
  graph.py       DependencyGraph
  scheduler.py   schedule(), CycleError, cycle finding
  critical_path.py   longest dependency chain
  guided.py      the guided menu interface
  dates.py       friendly date and importance parsing for the menu
  storage.py     JSON loading and saving, strict value parsing
main.py          entry point (guided menu, or typed commands with --commands)
USAGE.md         how to use the program, step by step
examples/        sample JSON inputs
tests/           unit tests
DECISIONS.md     design decisions and revisions
AI_USAGE.md      how AI tools were used
```

## Tests

```bash
python -m unittest -v
```

The suite has 188 tests. It covers input validation, ordering rules, cycle reporting, critical-path analysis, graph editing and renaming, date parsing, saving and loading, the guided menu (driven by scripted answers, including bad input, cancelling, editing, and refusing loops), typed commands, and the program run as a real process, including on consoles that cannot show every character. Two tests use random acyclic graphs: one checks that every dependency is respected in the schedule, and one compares the critical-path length against a separate brute-force search over all paths.

## Limitations

- The scheduler is greedy: it picks the best ready task each time. It does not guarantee that every deadline is met, and it does not know how long tasks take.
- The critical path assumes unlimited parallel workers, while `schedule()` produces a single sequence. The critical-path length is therefore a lower bound on completion time, not the length of the printed schedule.
- Durations are used only by `critical`. They do not affect the order produced by `schedule`.
- Only one cycle is reported at a time. If a graph has several, fix one and run again.
- Tasks are kept in memory until you save them (the Save option in the menu). The menu saves to `my_tasks.json` in the current folder.
- The typed `edit` command changes a task's name, priority, deadline or days. It cannot change what a task waits for, and typed mode has no command to remove a link; use the menu for those.
- The guided menu refuses a link that would create a loop. The core `DependencyGraph` does not, so a loop can still arrive from a loaded file; `schedule()` reports it.
- Dates in the menu are read day first (`05/11/2026` is 5 November).
