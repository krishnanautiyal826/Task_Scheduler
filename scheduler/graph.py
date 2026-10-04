from collections import deque
from typing import Optional

from .task import Task


class DependencyGraph:
    """Directed graph. An edge A -> B means A must finish before B starts."""

    def __init__(self):
        self.tasks: dict[str, Task] = {}
        self.dependents: dict[str, set[str]] = {}     # A -> {tasks that need A}
        self.prerequisites: dict[str, set[str]] = {}  # B -> {tasks B needs}

    def add_task(self, task: Task) -> None:
        if task.id in self.tasks:
            raise ValueError(f"Task '{task.id}' already exists")
        self.tasks[task.id] = task
        self.dependents[task.id] = set()
        self.prerequisites[task.id] = set()

    def add_dependency(self, task_id: str, depends_on_id: str) -> None:
        """Declare that task_id cannot start until depends_on_id is done."""
        for tid in (task_id, depends_on_id):
            if tid not in self.tasks:
                raise KeyError(f"Unknown task '{tid}'")
        if task_id == depends_on_id:
            raise ValueError(f"Task '{task_id}' cannot depend on itself")
        self.dependents[depends_on_id].add(task_id)
        self.prerequisites[task_id].add(depends_on_id)

    def in_degree(self, task_id: str) -> int:
        return len(self.prerequisites[task_id])

    def replace_task(self, old_id: str, new_task: Task) -> None:
        """Change a task's details, and optionally rename it.

        The task keeps its place in the list and every link it has, including
        the links other tasks have to it, even when it is renamed."""
        if old_id not in self.tasks:
            raise KeyError(f"Unknown task '{old_id}'")
        new_id = new_task.id
        if new_id != old_id and new_id in self.tasks:
            raise ValueError(f"Task '{new_id}' already exists")
        if new_id == old_id:
            self.tasks[old_id] = new_task
            return

        def rename(x):
            return new_id if x == old_id else x

        self.tasks = {rename(k): (new_task if k == old_id else v) for k, v in self.tasks.items()}
        self.dependents = {rename(k): {rename(x) for x in v} for k, v in self.dependents.items()}
        self.prerequisites = {rename(k): {rename(x) for x in v} for k, v in self.prerequisites.items()}

    def remove_dependency(self, task_id: str, depends_on_id: str) -> None:
        """Undo add_dependency: task_id no longer waits for depends_on_id."""
        for tid in (task_id, depends_on_id):
            if tid not in self.tasks:
                raise KeyError(f"Unknown task '{tid}'")
        if depends_on_id not in self.prerequisites[task_id]:
            raise ValueError(f"'{task_id}' does not wait for '{depends_on_id}'")
        self.prerequisites[task_id].discard(depends_on_id)
        self.dependents[depends_on_id].discard(task_id)

    def remove_task(self, task_id: str) -> None:
        """Delete a task and every dependency that touches it."""
        if task_id not in self.tasks:
            raise KeyError(f"Unknown task '{task_id}'")
        for waiting in self.dependents[task_id]:
            self.prerequisites[waiting].discard(task_id)
        for needed in self.prerequisites[task_id]:
            self.dependents[needed].discard(task_id)
        del self.tasks[task_id], self.dependents[task_id], self.prerequisites[task_id]

    def find_path(self, start: str, end: str) -> Optional[list]:
        """Shortest chain start -> ... -> end following 'must finish before' edges.

        Returns the list of task ids, or None if there is no such chain.
        Used to refuse a dependency that would create a loop. O(V + E).
        """
        for tid in (start, end):
            if tid not in self.tasks:
                raise KeyError(f"Unknown task '{tid}'")
        previous = {start: None}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            if node == end:
                path = []
                while node is not None:
                    path.append(node)
                    node = previous[node]
                return path[::-1]
            for nxt in sorted(self.dependents[node]):
                if nxt not in previous:
                    previous[nxt] = node
                    queue.append(nxt)
        return None

