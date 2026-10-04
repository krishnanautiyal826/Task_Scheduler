from typing import Optional

from .graph import DependencyGraph
from .scheduler import schedule
from .task import Task


def critical_path(graph: DependencyGraph) -> tuple[list[Task], int]:
    """Return the longest chain of dependent tasks and its total duration.

    Assumes unlimited parallel workers, so the total is the shortest
    possible time to finish everything. Raises CycleError on a cycle.
    """
    order = schedule(graph)               # a valid topological order
    finish: dict[str, int] = {}           # earliest finish time of each task
    previous: dict[str, Optional[str]] = {}  # which prerequisite set that time

    for task in order:
        best_prev = None
        for p in graph.prerequisites[task.id]:
            # the longest-finishing prerequisite decides when this task can start;
            # ties go to the smaller id so results are deterministic
            if (best_prev is None or finish[p] > finish[best_prev]
                    or (finish[p] == finish[best_prev] and p < best_prev)):
                best_prev = p
        start = finish[best_prev] if best_prev else 0
        finish[task.id] = start + task.duration
        previous[task.id] = best_prev

    if not order:
        return [], 0

    end = None
    for tid in finish:
        if end is None or finish[tid] > finish[end] or (finish[tid] == finish[end] and tid < end):
            end = tid

    total = finish[end]
    path = []
    node = end
    while node is not None:               # walk back from the last task
        path.append(graph.tasks[node])
        node = previous[node]
    return path[::-1], total
