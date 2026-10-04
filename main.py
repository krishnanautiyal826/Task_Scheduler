"""Task Scheduler.

Run:  python main.py                      guided menu (recommended)
      python main.py --demo               guided menu with an example loaded
      python main.py --file my.json       guided menu, tasks loaded from a file
      python main.py --commands           typed commands (advanced)
"""
import argparse
import os
import sys

from scheduler.critical_path import critical_path
from scheduler.graph import DependencyGraph
from scheduler.guided import GuidedApp
from scheduler.scheduler import CycleError, schedule
from scheduler.storage import DEMO_FILE, load_file, parse_date, parse_int
from scheduler.task import Task

HELP = """Commands:
  add <id> <priority 1-5> <YYYY-MM-DD> [days]   create a task (days defaults to 1)
  depend <task> <needs>                  <task> cannot start until <needs> is done
  list                                   show all tasks and dependencies
  schedule                               print a valid completion order
  critical                               longest chain of dependent tasks
  edit <task> <field> <value>            change a task; field is name, priority, deadline or days
  demo                                   load a small example (empty scheduler only)
  help | quit"""


def format_list(graph: DependencyGraph) -> str:
    if not graph.tasks:
        return "No tasks yet."
    lines = []
    for tid in sorted(graph.tasks):
        t = graph.tasks[tid]
        needs = ", ".join(sorted(graph.prerequisites[tid])) or "-"
        lines.append(f"{tid:<12} priority {t.priority}  due {t.deadline}  "
                     f"{t.duration}d  needs: {needs}")
    return "\n".join(lines)


def format_schedule(graph: DependencyGraph) -> str:
    order = schedule(graph)
    if not order:
        return "No tasks to schedule."
    return "\n".join(
        f"{i}. {t.id}  (due {t.deadline}, priority {t.priority})"
        for i, t in enumerate(order, 1)
    )


def format_critical(graph: DependencyGraph) -> str:
    path, total = critical_path(graph)
    if not path:
        return "No tasks yet."
    return f"Critical path ({total} days): " + " -> ".join(t.id for t in path)


EDIT_FIELDS = ("name", "priority", "deadline", "days")


def edit_task(graph: DependencyGraph, args) -> str:
    """edit <task> <field> <value>. Raises ValueError/KeyError like the other commands."""
    if len(args) != 3 or args[1].lower() not in EDIT_FIELDS:
        return "Usage: edit <task> <name|priority|deadline|days> <new value>"
    task_id, field, value = args[0], args[1].lower(), args[2]
    if task_id not in graph.tasks:
        raise KeyError(f"Unknown task '{task_id}'")
    old = graph.tasks[task_id]
    new_id, priority, deadline, days = old.id, old.priority, old.deadline, old.duration
    if field == "name":
        new_id = value
    elif field == "priority":
        priority = parse_int("priority", value)
    elif field == "deadline":
        deadline = parse_date(value)
    else:
        days = parse_int("days", value)
    graph.replace_task(task_id, Task(new_id, priority, deadline, days))
    return f"Changed '{task_id}': {field} is now {value}."


def handle(graph: DependencyGraph, line: str):
    """Run one command. Returns text to print, or None to quit."""
    parts = line.split()
    if not parts:
        return ""
    cmd, args = parts[0].lower(), parts[1:]
    try:
        if cmd in ("quit", "exit"):
            return None
        if cmd == "help":
            return HELP
        if cmd == "add":
            if len(args) not in (3, 4):
                return "Usage: add <id> <priority 1-5> <YYYY-MM-DD> [days]"
            days = parse_int("days", args[3]) if len(args) == 4 else 1
            graph.add_task(Task(args[0], parse_int("priority", args[1]),
                                parse_date(args[2]), days))
            return f"Added '{args[0]}'."
        if cmd == "depend":
            if len(args) != 2:
                return "Usage: depend <task> <needs>"
            graph.add_dependency(args[0], args[1])
            return f"'{args[0]}' now waits for '{args[1]}'."
        if cmd == "list":
            return format_list(graph)
        if cmd == "schedule":
            return format_schedule(graph)
        if cmd == "critical":
            return format_critical(graph)
        if cmd == "edit":
            return edit_task(graph, args)
        if cmd == "demo":
            if graph.tasks:
                return "The demo only loads into an empty scheduler. Restart to use it."
            load_file(graph, DEMO_FILE)
            return "Demo loaded. Try: list, schedule, critical"
        return f"Unknown command '{cmd}'. Type 'help'."
    except CycleError as e:
        msg = f"Cannot continue. {e}"
        if e.blocked:
            msg += f"\nAlso blocked by the cycle: {', '.join(e.blocked)}"
        return msg
    except KeyError as e:
        return f"Error: {e.args[0]}"
    except (ValueError, OSError) as e:
        return f"Error: {e}"


def run_commands(graph: DependencyGraph) -> None:
    try:
        print("Task Scheduler (typed commands). Type 'help' for commands.")
        while True:
            try:
                line = input("> ")
            except EOFError:
                print()
                break
            out = handle(graph, line)
            if out is None:
                break
            if out:
                print(out)
    except KeyboardInterrupt:
        print()


def make_streams_forgiving() -> None:
    """Never crash because of a character the console cannot show or read.

    Some consoles (for example older Windows ones, or when output is redirected)
    use an encoding that cannot represent every character. Unusable characters
    become '?' instead of raising an error and losing the user's work.
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def main() -> None:
    make_streams_forgiving()
    try:
        _main()
    except BrokenPipeError:
        # the reader of our output (for example `| head`) went away: exit quietly
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except (OSError, ValueError):
            pass
        sys.exit(1)


def _main() -> None:
    parser = argparse.ArgumentParser(description="Dependency-aware task scheduler")
    parser.add_argument("--file", help="load tasks from a JSON file")
    parser.add_argument("--demo", action="store_true", help="load the built-in example")
    parser.add_argument("--commands", action="store_true",
                        help="use typed commands instead of the guided menu")
    opts = parser.parse_args()

    graph = DependencyGraph()
    try:
        if opts.demo:
            load_file(graph, DEMO_FILE)
        if opts.file:
            load_file(graph, opts.file)
    except (OSError, ValueError) as e:
        sys.exit(f"Could not load tasks: {e}")

    if opts.commands:
        run_commands(graph)
    else:
        # when tasks were loaded on purpose, don't also offer a saved list
        GuidedApp(graph).run(offer_saved=not (opts.demo or opts.file))


if __name__ == "__main__":
    main()
