from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from quartermaster.domain.models import Environment, EnvironmentKind, LocatorStrategy

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


class FakeDriver:
    """In-memory page: `elements` maps (strategy, value) -> match count."""

    def __init__(self, elements: dict[tuple[str, str], int] | None = None, texts: dict[str, str] | None = None):
        self.elements = {(LocatorStrategy(s), v): n for (s, v), n in (elements or {}).items()}
        self.texts = texts or {}
        self.calls: list[tuple[Any, ...]] = []
        self.job_status = "SUCCEEDED"
        self.api_status = 200
        self.opened = self.closed = False

    def open(self, env: Environment, persona: str) -> None:
        self.opened = True
        self.calls.append(("open", persona))

    def login_as(self, persona: str) -> None:
        self.calls.append(("login_as", persona))

    def close(self) -> None:
        self.closed = True

    def count(self, strategy: LocatorStrategy, value: str) -> int:
        return self.elements.get((strategy, value), 0)

    def navigate(self, path: str) -> None:
        self.calls.append(("navigate", path))

    def click(self, strategy: LocatorStrategy, value: str) -> None:
        self.calls.append(("click", strategy.value, value))

    def fill(self, strategy: LocatorStrategy, value: str, text: str) -> None:
        self.calls.append(("fill", strategy.value, value, text))

    def select(self, strategy: LocatorStrategy, value: str, option: str) -> None:
        self.calls.append(("select", strategy.value, value, option))

    def text_of(self, strategy: LocatorStrategy, value: str) -> str:
        return self.texts.get(value, "")

    def wait_job(self, job_name: str, timeout_s: float) -> str:
        self.calls.append(("wait_job", job_name))
        return self.job_status

    def api_call(self, request: str, options: dict[str, Any]) -> int:
        self.calls.append(("api_call", request))
        return self.api_status

    def screenshot(self, name: str) -> str | None:
        return f"evidence/{name}.png"


@pytest.fixture
def stage_env() -> Environment:
    return Environment(name="stage", url="https://abcd-test.fa.us2.oraclecloud.com", kind=EnvironmentKind.STAGE)
