"""Environment-backed worker configuration with safe defaults."""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class WorkerConfig:
    model_provider: str = "flexible"
    model_name: str | None = None
    environment: str = "development"

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        provider = os.getenv("RUSAAI_MODEL_PROVIDER", "flexible").strip().lower()
        if provider != "flexible":
            raise ValueError(
                "Only provider='flexible' is enabled in this bootstrap. "
                "Concrete provider adapters require an explicit implementation and review."
            )
        model_name = os.getenv("RUSAAI_MODEL_NAME") or None
        environment = os.getenv("RUSAAI_ENVIRONMENT", "development").strip().lower()
        if environment not in {"development", "test", "staging", "production"}:
            raise ValueError("RUSAAI_ENVIRONMENT must be development, test, staging, or production")
        return cls(model_provider=provider, model_name=model_name, environment=environment)
