from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Task:
    id: str
    priority: int      # 1 (low) to 5 (high)
    deadline: date
    duration: int = 1  # whole days; used only by critical-path analysis

    def __post_init__(self):
        if not self.id.strip():
            raise ValueError("Task id cannot be empty")
        if not 1 <= self.priority <= 5:
            raise ValueError("Priority must be between 1 and 5")
        if self.duration < 1:
            raise ValueError("Duration must be at least 1 day")
