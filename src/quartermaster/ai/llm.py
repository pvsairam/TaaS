"""LLM provider abstraction.

Agents depend on the `LLM` protocol only, so tests use `FakeLLM` and a tenant can run with
AI disabled. Every prompt passes through PII masking before it leaves the process.
"""

from __future__ import annotations

from collections import deque
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel

from quartermaster.ai.masking import mask

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "claude-opus-5"

Effort = Literal["low", "medium", "high", "xhigh", "max"]


class LLMError(RuntimeError):
    pass


class LLM(Protocol):
    def structured(self, system: str, prompt: str, schema: type[T]) -> T: ...


class ClaudeLLM:
    """Claude via the official Anthropic SDK, with schema-validated structured output."""

    def __init__(self, model: str = DEFAULT_MODEL, effort: Effort = "high"):
        import anthropic  # optional dependency: pip install quartermaster[ai]

        self._anthropic = anthropic
        self._client = anthropic.Anthropic()
        self._model = model
        self._effort = effort

    def structured(self, system: str, prompt: str, schema: type[T]) -> T:
        try:
            response = self._client.messages.parse(
                model=self._model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": mask(prompt)}],
                output_format=schema,
                thinking={"type": "adaptive"},
                output_config={"effort": self._effort},
                # Server-side fallback: if a request is declined, the API retries it on
                # Anthropic's recommended fallback model instead of returning a refusal.
                extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
                extra_body={"fallbacks": "default"},
            )
        except self._anthropic.RateLimitError as e:
            raise LLMError("Claude rate limit reached; retry later") from e
        except self._anthropic.APIStatusError as e:
            raise LLMError(f"Claude API error {e.status_code}: {e.message}") from e
        except self._anthropic.APIConnectionError as e:
            raise LLMError("could not reach the Claude API") from e

        if response.stop_reason == "refusal":
            raise LLMError("model declined the request")
        if response.stop_reason == "max_tokens" or response.parsed_output is None:
            raise LLMError(f"no structured output (stop_reason={response.stop_reason})")
        return response.parsed_output


class FakeLLM:
    """Deterministic stand-in for tests: returns queued responses and records prompts."""

    def __init__(self, *responses: BaseModel):
        self._responses: deque[BaseModel] = deque(responses)
        self.prompts: list[str] = []

    def structured(self, system: str, prompt: str, schema: type[T]) -> T:
        self.prompts.append(mask(prompt))
        if not self._responses:
            raise LLMError("FakeLLM has no queued responses")
        out = self._responses.popleft()
        if not isinstance(out, schema):
            raise LLMError(f"FakeLLM queued {type(out).__name__}, caller expected {schema.__name__}")
        return out
