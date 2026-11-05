"""Queue contract. A durable backend is intentionally not selected yet."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerTask:
    task_id: str
    payload: dict


class TaskQueue(ABC):
    @abstractmethod
    def claim(self) -> WorkerTask | None:
        """Atomically claim one task using a lease in the concrete backend."""
        raise NotImplementedError

    @abstractmethod
    def acknowledge(self, task_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def retry(self, task_id: str, reason: str) -> None:
        raise NotImplementedError
