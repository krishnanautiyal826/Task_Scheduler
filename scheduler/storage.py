"""Reading and writing task lists as JSON, plus strict value parsing."""
import json
import os
import re
import tempfile
from datetime import date
from pathlib import Path

from .graph import DependencyGraph
from .task import Task

MAX_NUMBER = 999_999_999
DEMO_FILE = Path(__file__).resolve().parent.parent / "examples" / "tasks.json"


def parse_int(label: str, value) -> int:
    """Accept whole numbers only (not 3.5, 'abc', or true/false)."""
    if isinstance(value, int) and not isinstance(value, bool):
        if abs(value) > MAX_NUMBER:
            raise ValueError(f"{label} is too large (the limit is {MAX_NUMBER})")
        return value
    if isinstance(value, str) and re.fullmatch(r"-?[0-9]{1,9}", value):
        return int(value)
    raise ValueError(f"{label} must be a whole number (up to 9 digits), got {value[:30]!r}"
                     if isinstance(value, str) else f"{label} must be a whole number, got {value!r}")


def parse_date(value) -> date:
    """Strict YYYY-MM-DD, so behaviour does not vary by Python version."""
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise ValueError(f"deadline must be a real date written YYYY-MM-DD, got {value!r}")


def load_data(graph: DependencyGraph, data) -> None:
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        raise ValueError('the file must be a JSON object with a "tasks" list')
    for i, t in enumerate(data["tasks"], 1):
        if not isinstance(t, dict):
            raise ValueError(f"task #{i} must be an object")
        for key in ("id", "priority", "deadline"):
            if key not in t:
                raise ValueError(f"task #{i} is missing '{key}'")
        graph.add_task(Task(str(t["id"]),
                            parse_int("priority", t["priority"]),
                            parse_date(t["deadline"]),
                            parse_int("duration", t.get("duration", 1))))
    deps = data.get("dependencies", [])
    if not isinstance(deps, list):
        raise ValueError('"dependencies" must be a list')
    for i, d in enumerate(deps, 1):
        if not (isinstance(d, list) and len(d) == 2):
            raise ValueError(f'dependency #{i} must be a pair like ["task", "needs"]')
        try:
            graph.add_dependency(str(d[0]), str(d[1]))
        except KeyError as e:
            raise ValueError(e.args[0]) from None


def load_file(graph: DependencyGraph, path) -> None:
    with open(path, encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"not valid JSON ({e.msg}, line {e.lineno})") from None
        except RecursionError:
            raise ValueError("the file is nested too deeply to be a task list") from None
    load_data(graph, data)


def graph_to_data(graph: DependencyGraph) -> dict:
    """The same shape load_data reads, so save then load round-trips."""
    tasks = [{"id": t.id, "priority": t.priority,
              "deadline": t.deadline.isoformat(), "duration": t.duration}
             for t in graph.tasks.values()]
    deps = sorted([tid, need] for tid, needs in graph.prerequisites.items()
                  for need in needs)
    return {"tasks": tasks, "dependencies": deps}


def _file_mode(path: Path) -> int:
    """Keep an existing file's permissions; a new file gets the usual default.
    (mkstemp creates private 0600 files, which would surprise people.)"""
    if path.exists():
        return path.stat().st_mode & 0o777
    umask = os.umask(0)
    os.umask(umask)
    return 0o666 & ~umask


def save_file(graph: DependencyGraph, path) -> None:
    """Write atomically: a crash mid-save cannot leave a half-written file."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(graph_to_data(graph), f, indent=2)
            f.write("\n")
        os.chmod(tmp, _file_mode(path))
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
