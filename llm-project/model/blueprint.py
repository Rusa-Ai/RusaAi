from dataclasses import dataclass, field
from typing import List


@dataclass
class MoESpec:
    enabled: bool = True
    num_experts: int = 64
    experts_per_token: int = 2

    def validate(self) -> None:
        if self.num_experts <= 0:
            raise ValueError("num_experts must be positive")
        if self.experts_per_token <= 0:
            raise ValueError("experts_per_token must be positive")
        if self.enabled and self.experts_per_token > self.num_experts:
            raise ValueError("experts_per_token cannot exceed num_experts")


@dataclass
class ModelSpec:
    name: str = "rusa-ai-base-blueprint"
    model_type: str = "decoder-only-transformer"
    layers: int = 96
    hidden_size: int = 12288
    attention_heads: int = 96
    kv_heads: int = 8
    context_window: int = 1_000_000
    positional_encoding: str = "rope"
    normalization: str = "rmsnorm"
    activation: str = "swiglu"
    modalities: List[str] = field(default_factory=lambda: ["text", "image"])
    moe: MoESpec = field(default_factory=MoESpec)

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("model name must not be empty")
        if self.layers <= 0:
            raise ValueError("layers must be positive")
        if self.hidden_size <= 0:
            raise ValueError("hidden_size must be positive")
        if self.attention_heads <= 0:
            raise ValueError("attention_heads must be positive")
        if self.kv_heads <= 0:
            raise ValueError("kv_heads must be positive")
        if self.hidden_size % self.attention_heads != 0:
            raise ValueError("hidden_size must be divisible by attention_heads")
        if self.attention_heads % self.kv_heads != 0:
            raise ValueError("attention_heads must be divisible by kv_heads")
        if self.context_window <= 0:
            raise ValueError("context_window must be positive")
        if not self.modalities or any(not item.strip() for item in self.modalities):
            raise ValueError("modalities must contain non-empty values")
        if len(set(self.modalities)) != len(self.modalities):
            raise ValueError("modalities must not contain duplicates")
        self.moe.validate()


@dataclass
class TrainingSpec:
    objective: str = "next_token_prediction"
    precision: str = "bf16"
    post_training: List[str] = field(
        default_factory=lambda: [
            "supervised_fine_tuning",
            "rlhf_rlaif",
            "reasoning_rl",
            "safety_alignment",
        ]
    )


@dataclass
class InferenceSpec:
    quantization: List[str] = field(default_factory=lambda: ["int8", "fp8"])
    speculative_decoding: bool = True
    tool_use: bool = True


@dataclass
class ProjectBlueprint:
    model: ModelSpec = field(default_factory=ModelSpec)
    training: TrainingSpec = field(default_factory=TrainingSpec)
    inference: InferenceSpec = field(default_factory=InferenceSpec)
    status: str = "PLANNED"

    def validate(self) -> None:
        self.model.validate()


if __name__ == "__main__":
    blueprint = ProjectBlueprint()
    blueprint.validate()
    print(blueprint)
