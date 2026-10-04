# AI Usage

## Tool

Claude (Anthropic), used through the chat interface.

## What AI was used for

- Choosing which project to build from the task list
- Proposing the project structure and the order to build it in
- Generating the code one module at a time: task model, graph, scheduler, cycle reporting, CLI, critical path
- Redesigning the interface after I found it hard to use: a guided menu, friendly date parsing, undo (remove task or link), saving, and USAGE.md
- Auditing the finished program for bugs, fixing what was found, and adding a "change a task" command
- Writing the unit tests
- Drafting this README, DECISIONS.md and this file

## How it was used

The code was built in separate steps. Each step was explained before the next one began, and the reasoning for each design choice was written down alongside the code.

## How the output was checked

- Each module was run on small examples before moving on.
- The unit tests (188) were run against the final code and pass, on Python 3.11, 3.12 and 3.13.
- To confirm the tests can fail, the code was deliberately broken in two ways: flipping the priority sign in the heap key (1 test failed) and disabling the cycle check (7 tests failed). The original code was then restored and all tests passed. The same was done for the critical-path code: choosing the shortest instead of the longest chain made 2 tests fail, and ignoring durations made 8 fail.
- The critical-path length is also checked against an independent brute-force search over all paths on 100 random graphs.
- Running the CLI end to end found bugs that were then fixed: a duplicated error message for unknown tasks, a demo path that only worked from the project folder, error messages that exposed raw Python text (for example `invalid literal for int()`), and a date parser that accepted `20261101` on Python 3.11+ but not on older versions.
- Earlier, a pass broke the code in 35 different ways (for example reversing the cycle direction, dropping the loop check in the menu, swapping day and month in dates, skipping the confirmation before removing a task) and ran the suite each time. The first run caught 32 of 35. The 3 that survived exposed real gaps in my tests (no check that `find_path` handles a graph that already has a loop, and no check that removing a link or saving updates the unsaved-changes flag), so tests were added and all 35 are now caught. This shows the tests are sensitive to those changes, not that the code is free of bugs.
- **Bug audit.** After the interface was built, I asked for a bug check and the code was attacked on purpose: odd and hostile inputs to every parser and to the file loader, random testing (about 24,000 random menu sessions and several hundred thousand random inputs to the parsers, the loader and the typed commands, over three random seeds), a lint pass, and runs under restricted console settings. Each random menu session checked that the graph stayed internally consistent and that a valid plan could still be produced. This found 14 problems that the ordinary tests had missed, including crashes on far-future dates, on characters such as `²`, on very deeply nested files, and on consoles that cannot show arrows, plus one case of silent data loss (declining to load a saved list and then saving replaced it). All 14 are fixed, and each has a regression test. The regression tests for the first group of fixes were also run against the pre-fix code, and 16 of them failed there, as they should. The problems are listed in DECISIONS.md, item 15.
- **Edit command.** The change-a-task feature was tested at three levels (the graph, the menu, the typed command), including renaming, cancelling part-way, and refusing a link that would make a loop. A random test applies hundreds of renames and edits to random graphs and checks that no link is lost or invented.
- A later pass broke the code in 71 different ways, including the edit logic, the loop refusal when editing, the safe-saving checks and each of the audit fixes. The first run caught 66 of 69 (two more had patterns that no longer matched the changed code and were updated). The 3 that survived were real gaps in my tests: a test that saved twice with identical content and so could not tell whether the file was recognised as the program's own; no test for replacing an empty saved list; and no test for oversized numbers inside a JSON file. Tests were added and all 71 are now caught.
- The suite was run 5 times and under 6 different hash seeds with the same result, to rule out dependence on set ordering.
- Graphs of 100,000 tasks (a long chain, a long cycle, and a wide fan-out) were scheduled in under a second without hitting Python's recursion limit. This is a one-off check, not a benchmark.
- An early complexity claim of O((V + E) log V) was corrected to the tighter O(V log V + E).

## Limits of the checking

- Tests cover correctness on small and randomly generated graphs. There are no performance benchmarks.
- Line and branch coverage of `scheduler/` is 100% of lines and 99% counting branches. `main.py` reads lower because `main()` is tested by running it as a separate process, which the coverage tool does not measure.
- The menu was checked with scripted answers and by running the real program with piped input. It has not been tried by a person unfamiliar with the project, so "intuitive" is my judgement from reading real sessions, not a measured result.
- The minimum Python version (3.9) was checked with a static tool and a syntax check set to 3.9 rules. The tests were run on 3.11, 3.12 and 3.13, not on 3.9 or 3.10.
- The random testing checks that the program does not crash and stays consistent. It cannot judge whether a message reads well, and finding nothing more does not prove nothing is left.
- The typed-command mode cannot remove a link or change what a task waits for. That gap is stated in the README and DECISIONS.md rather than hidden.
- The AI-generated code is only as reliable as the tests that exercise it.
