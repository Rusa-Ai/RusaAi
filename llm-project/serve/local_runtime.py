"""Local-only OpenAI-compatible inference client for RUSA-AI.

This adapter talks to a model server already running on loopback (for example,
Ollama's OpenAI-compatible endpoint). It does not download weights or call a
hosted API. The caller remains responsible for installing and licensing a
local model before inference.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_MAX_TOKENS = 8192
_ALLOWED_ROLES = {"system", "user", "assistant"}


class LocalRuntimeError(RuntimeError):
    """Raised when the local model endpoint cannot satisfy a request."""


@dataclass(frozen=True)
class RuntimeConfig:
    base_url: str = "http://127.0.0.1:11434/v1"
    model: str | None = None
    timeout_seconds: float = 60.0
    max_tokens: int = 512

    def __post_init__(self) -> None:
        parsed = urllib.parse.urlsplit(self.base_url)
        if parsed.scheme != "http":
            raise ValueError("base_url must use plain HTTP on loopback")
        if not parsed.hostname:
            raise ValueError("base_url must include a loopback host")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("base_url must not contain credentials, query, or fragment")
        try:
            parsed.port  # Validate malformed/out-of-range ports.
        except ValueError as exc:
            raise ValueError("base_url contains an invalid port") from exc

        hostname = parsed.hostname.lower()
        is_loopback = hostname == "localhost"
        if not is_loopback:
            try:
                is_loopback = ipaddress.ip_address(hostname).is_loopback
            except ValueError:
                is_loopback = False
        if not is_loopback:
            raise ValueError("base_url host must be localhost or a loopback IP address")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not 1 <= self.max_tokens <= _MAX_TOKENS:
            raise ValueError(f"max_tokens must be between 1 and {_MAX_TOKENS}")
        if self.model is not None and not self.model.strip():
            raise ValueError("model must be non-empty when provided")

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        timeout_raw = os.getenv("RUSA_MODEL_TIMEOUT_SECONDS", "60")
        max_tokens_raw = os.getenv("RUSA_MODEL_MAX_TOKENS", "512")
        try:
            timeout = float(timeout_raw)
            max_tokens = int(max_tokens_raw)
        except ValueError as exc:
            raise ValueError("RUSA model timeout/max-token environment values are invalid") from exc
        return cls(
            base_url=os.getenv("RUSA_MODEL_BASE_URL", "http://127.0.0.1:11434/v1"),
            model=os.getenv("RUSA_MODEL_NAME") or None,
            timeout_seconds=timeout,
            max_tokens=max_tokens,
        )


@dataclass(frozen=True)
class RuntimeHealth:
    process_reachable: bool
    model_available: bool | None
    available_models: tuple[str, ...]


class LocalOpenAICompatibleRuntime:
    """Small standard-library client with a strict loopback-only network policy."""

    def __init__(self, config: RuntimeConfig, opener: Any = urllib.request.urlopen):
        self.config = config
        self._opener = opener
        self._base_url = config.base_url.rstrip("/")

    def _request(self, path: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self._base_url}/{path.lstrip('/')}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json"}
        method = "GET" if data is None else "POST"
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self._opener(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            raise LocalRuntimeError(f"local model endpoint returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LocalRuntimeError(f"cannot reach local model endpoint: {exc}") from exc

        if len(raw) > _MAX_RESPONSE_BYTES:
            raise LocalRuntimeError("local model response exceeded the 2 MiB safety limit")
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LocalRuntimeError("local model endpoint returned invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise LocalRuntimeError("local model endpoint returned an unexpected JSON shape")
        return parsed

    def list_models(self) -> tuple[str, ...]:
        payload = self._request("models")
        data = payload.get("data")
        if not isinstance(data, list):
            raise LocalRuntimeError("models response must contain a data array")
        model_ids: list[str] = []
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                model_ids.append(item["id"])
        return tuple(model_ids)

    def health(self, model: str | None = None) -> RuntimeHealth:
        models = self.list_models()
        target = model or self.config.model
        return RuntimeHealth(
            process_reachable=True,
            model_available=(target in models) if target else None,
            available_models=models,
        )

    def complete(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> str:
        selected_model = model or self.config.model
        if not selected_model or not selected_model.strip():
            raise ValueError("set RUSA_MODEL_NAME or pass model= before requesting inference")
        if not messages:
            raise ValueError("messages must contain at least one message")
        normalized_messages: list[dict[str, str]] = []
        for item in messages:
            role = item.get("role")
            content = item.get("content")
            if role not in _ALLOWED_ROLES:
                raise ValueError("message role must be system, user, or assistant")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("message content must be a non-empty string")
            normalized_messages.append({"role": role, "content": content})

        token_limit = self.config.max_tokens if max_tokens is None else max_tokens
        if not 1 <= token_limit <= _MAX_TOKENS:
            raise ValueError(f"max_tokens must be between 1 and {_MAX_TOKENS}")
        if not 0 <= temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")

        payload = self._request(
            "chat/completions",
            {
                "model": selected_model,
                "messages": normalized_messages,
                "max_tokens": token_limit,
                "temperature": temperature,
                "stream": False,
            },
        )
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LocalRuntimeError("chat completion response is missing choices[0].message.content") from exc
        if not isinstance(content, str):
            raise LocalRuntimeError("chat completion content must be text")
        return content


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RUSA-AI local-only model runtime client")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("health", help="check local endpoint and optional model availability")
    chat = subparsers.add_parser("chat", help="send one non-streaming chat request")
    chat.add_argument("--model", help="installed local model ID (or set RUSA_MODEL_NAME)")
    chat.add_argument("--message", required=True, help="user message to send")
    chat.add_argument("--max-tokens", type=int, help="maximum generated tokens")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        config = RuntimeConfig.from_env()
        runtime = LocalOpenAICompatibleRuntime(config)
        if args.command == "health":
            status = runtime.health()
            print(json.dumps({
                "process_reachable": status.process_reachable,
                "model_available": status.model_available,
                "available_models": list(status.available_models),
            }, indent=2))
            return 0 if status.process_reachable and status.model_available is not False else 1
        answer = runtime.complete(
            [{"role": "user", "content": args.message}],
            model=args.model,
            max_tokens=args.max_tokens,
        )
        print(answer)
        return 0
    except (LocalRuntimeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
