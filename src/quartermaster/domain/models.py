"""Core domain model for Quartermaster.

Everything that crosses a module boundary is one of these Pydantic models, so it is
validated once at the edge (YAML load, LLM output, API input) and trusted afterwards.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)


# --------------------------------------------------------------------------- environments


class EnvironmentKind(StrEnum):
    DEV = "DEV"
    TEST = "TEST"
    STAGE = "STAGE"
    PROD = "PROD"


class Environment(_Strict):
    name: str
    url: str
    kind: EnvironmentKind
    release: str | None = Field(default=None, description="Pod release, e.g. '26D'")


# --------------------------------------------------------------------------- releases


class ChangeType(StrEnum):
    UI = "UI"
    PROCESS = "PROCESS"
    BOTH = "BOTH"
    REPORT = "REPORT"
    API = "API"


class Feature(_Strict):
    """One row of Oracle's quarterly 'What's New' feature list."""

    id: str
    module: str = Field(description="Pillar/module, e.g. 'Financials', 'Procurement'")
    product: str = Field(description="Product within module, e.g. 'Payables'")
    title: str
    description: str = ""
    change_type: ChangeType = ChangeType.UI
    opt_in: bool = False
    customer_action_required: bool = False
    tags: list[str] = Field(default_factory=list)


class Release(_Strict):
    id: str = Field(pattern=r"^\d{2}[A-D]$", description="Oracle update id, e.g. '26D'")
    features: list[Feature] = Field(default_factory=list)


# --------------------------------------------------------------------------- tests


class LocatorStrategy(StrEnum):
    LABEL = "label"
    ROLE = "role"
    TEST_ID = "test_id"
    TEXT = "text"
    CSS = "css"
    XPATH = "xpath"


class Locator(_Strict):
    """An element described by several strategies, tried in the listed order."""

    strategies: list[dict[LocatorStrategy, str]] = Field(min_length=1)
    description: str = ""

    @field_validator("strategies")
    @classmethod
    def _one_key_each(cls, v: list[dict[LocatorStrategy, str]]) -> list[dict[LocatorStrategy, str]]:
        for s in v:
            if len(s) != 1:
                raise ValueError("each locator strategy must have exactly one key, e.g. {label: 'Supplier'}")
        return v

    def ordered(self) -> list[tuple[LocatorStrategy, str]]:
        return [next(iter(s.items())) for s in self.strategies]


class Action(StrEnum):
    NAVIGATE = "navigate"  # Fusion navigator path, e.g. "Payables > Invoices"
    CLICK = "click"
    FILL = "fill"
    SELECT = "select"
    ASSERT_VISIBLE = "assert_visible"
    ASSERT_TEXT = "assert_text"
    WAIT_JOB = "wait_job"  # ESS scheduled process
    API_CALL = "api_call"


_TARGETED = {Action.CLICK, Action.FILL, Action.SELECT, Action.ASSERT_VISIBLE, Action.ASSERT_TEXT}
_VALUED = {Action.NAVIGATE, Action.FILL, Action.SELECT, Action.ASSERT_TEXT, Action.WAIT_JOB, Action.API_CALL}


class Step(_Strict):
    action: Action
    intent: str = Field(description="Human-readable purpose; used by the healer and reports")
    target: Locator | None = None
    value: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_shape(self) -> Step:
        if self.action in _TARGETED and self.target is None:
            raise ValueError(f"action '{self.action.value}' requires a target")
        if self.action in _VALUED and self.value is None:
            raise ValueError(f"action '{self.action.value}' requires a value")
        return self


class Priority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


PRIORITY_WEIGHT: dict[Priority, float] = {
    Priority.CRITICAL: 1.0,
    Priority.HIGH: 0.8,
    Priority.MEDIUM: 0.5,
    Priority.LOW: 0.3,
}


class TestCase(_Strict):
    __test__ = False  # stop pytest from collecting this class

    id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    title: str
    module: str
    product: str
    process: str = ""
    persona: str = ""
    priority: Priority = Priority.MEDIUM
    tags: list[str] = Field(default_factory=list)
    estimated_minutes: float = Field(default=5.0, gt=0)
    data: dict[str, str] = Field(default_factory=dict)
    steps: list[Step] = Field(min_length=1)


# --------------------------------------------------------------------------- results


class StepStatus(StrEnum):
    PASSED = "passed"
    HEALED = "healed"
    FAILED = "failed"
    SKIPPED = "skipped"


class HealingProposal(_Strict):
    step_index: int
    intent: str
    old: tuple[LocatorStrategy, str]
    new: tuple[LocatorStrategy, str]
    confidence: float = Field(ge=0, le=1)
    source: str = "fallback"  # "fallback" | "ai"


class StepResult(_Strict):
    index: int
    intent: str
    status: StepStatus
    duration_ms: float = 0
    error: str | None = None
    evidence: list[str] = Field(default_factory=list)


class RunResult(_Strict):
    test_id: str
    environment: str
    steps: list[StepResult]
    healing: list[HealingProposal] = Field(default_factory=list)

    @property
    def status(self) -> StepStatus:
        statuses = {s.status for s in self.steps}
        if StepStatus.FAILED in statuses:
            return StepStatus.FAILED
        if StepStatus.HEALED in statuses:
            return StepStatus.HEALED
        return StepStatus.PASSED
