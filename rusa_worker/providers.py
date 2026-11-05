"""Provider-neutral contract. No network calls or secrets are used here."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class GenerationRequest:
    task_id: str
    prompt: str


@dataclass(frozen=True)
class GenerationResult:
    text: str
    provider: str
    model: str | None = None


class ModelProvider(ABC):
    @abstractmethod
    def generate(self, request: GenerationRequest) -> GenerationResult:
        """Generate a response; concrete adapters must implement this contract."""
        raise NotImplementedError


class FlexibleProvider(ModelProvider):
    def generate(self, request: GenerationRequest) -> GenerationResult:
        raise RuntimeError(
            "No model provider adapter is configured. The flexible contract is ready, "
            "but inference is intentionally disabled until an adapter is reviewed and configured."
        )
