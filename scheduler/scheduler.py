import heapq

from .graph import DependencyGraph
from .task import Task


class CycleError(Exception):
    """Raised when tasks depend on each other in a loop."""

    def __init__(self, cycle: list[str], blocked: list[str]):
        self.cycle = cycle      # e.g. ['a', 'b', 'c', 'a'], each must finish before the next
        self.blocked = blocked  # tasks stuck only because they wait on the cycle
        super().__init__("Circular dependency: " + " -> ".join(cycle))


def _key(task: Task) -> tuple:
    """Heap ordering: earliest deadline, then higher priority, then id."""
    return (task.deadline, -task.priority, task.id)


def _find_cycle(graph: DependencyGraph, leftover: set[str]) -> list[str]:
    """Walk backwards through prerequisites until a task repeats.

    Every leftover task still has an unfinished prerequisite, and that
    prerequisite is also in leftover, so the walk can never dead-end.
    """
    seen: dict[str, int] = {}
    path: list[str] = []
    node = min(leftover)                       # min() keeps the output deterministic
    while node not in seen:
        seen[node] = len(path)
        path.append(node)
        node = min(graph.prerequisites[node] & leftover)
    loop = path[seen[node]:][::-1]             # reverse so arrows mean "finishes before"
    return loop + [loop[0]]


def schedule(graph: DependencyGraph) -> list[Task]:
    """Return tasks in a valid order using Kahn's algorithm with a min-heap.

    Raises CycleError if the dependencies contain a loop.
    """
    # Working copy of in-degrees, so the graph itself is never modified.
    remaining = {tid: graph.in_degree(tid) for tid in graph.tasks}

    # Start with every task that has no prerequisites.
    heap = [_key(graph.tasks[tid]) for tid, d in remaining.items() if d == 0]
    heapq.heapify(heap)

    order: list[Task] = []
    while heap:
        _, _, tid = heapq.heappop(heap)       # best ready task
        order.append(graph.tasks[tid])
        for nxt in graph.dependents[tid]:     # tid is done: unblock dependents
            remaining[nxt] -= 1
            if remaining[nxt] == 0:           # all prerequisites finished
                heapq.heappush(heap, _key(graph.tasks[nxt]))

    if len(order) < len(graph.tasks):         # some tasks never became ready
        done = {t.id for t in order}
        leftover = set(graph.tasks) - done
        cycle = _find_cycle(graph, leftover)
        blocked = sorted(leftover - set(cycle))
        raise CycleError(cycle, blocked)
    return order
