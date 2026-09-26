"""Deterministic step executor.

The engine only knows the `Driver` protocol. `PlaywrightDriver` talks to a real Fusion pod;
tests use an in-memory fake. Business flows are sequential, so the first failed step skips
the rest.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any, Protocol

from quartermaster.domain.models import (
    Action,
    Environment,
    HealingProposal,
    LocatorStrategy,
    RunResult,
    Step,
    StepResult,
    StepStatus,
    TestCase,
)
from quartermaster.dsl.loader import render_value
from quartermaster.locators.resolver import Resolution, ResolutionError, resolve
from quartermaster.safety.guards import assert_safe_target


class Driver(Protocol):
    def open(self, env: Environment) -> None: ...
    def close(self) -> None: ...
    def count(self, strategy: LocatorStrategy, value: str) -> int: ...
    def navigate(self, path: str) -> None: ...
    def click(self, strategy: LocatorStrategy, value: str) -> None: ...
    def fill(self, strategy: LocatorStrategy, value: str, text: str) -> None: ...
    def select(self, strategy: LocatorStrategy, value: str, option: str) -> None: ...
    def text_of(self, strategy: LocatorStrategy, value: str) -> str: ...
    def wait_job(self, job_name: str, timeout_s: float) -> str: ...
    def api_call(self, request: str, options: dict[str, Any]) -> int: ...
    def screenshot(self, name: str) -> str | None: ...


# Called when every locator strategy fails; may return an AI-proposed replacement.
Healer = Callable[[int, Step, Driver], HealingProposal | None]


class StepFailure(AssertionError):
    pass


def run_test(
    test: TestCase,
    env: Environment,
    driver: Driver,
    *,
    allowed_hosts: set[str] | None = None,
    healer: Healer | None = None,
    run_id: str | None = None,
) -> RunResult:
    assert_safe_target(env, allowed_hosts)
    runtime = {"RUN_ID": run_id or uuid.uuid4().hex[:8].upper()}
    results: list[StepResult] = []
    healing: list[HealingProposal] = []

    driver.open(env)
    try:
        failed = False
        for i, step in enumerate(test.steps):
            if failed:
                results.append(StepResult(index=i, intent=step.intent, status=StepStatus.SKIPPED))
                continue
            start = time.perf_counter()
            status, error, evidence = StepStatus.PASSED, None, []
            try:
                res = _execute(step, test.data, runtime, driver)
                if res is not None and res.healed:
                    status = StepStatus.HEALED
                    healing.append(
                        HealingProposal(
                            step_index=i,
                            intent=step.intent,
                            old=step.target.ordered()[0],  # type: ignore[union-attr]
                            new=(res.strategy, res.value),
                            confidence=res.confidence,
                        )
                    )
            except ResolutionError as e:
                status, error = StepStatus.FAILED, str(e)
                if healer is not None:
                    proposal = healer(i, step, driver)
                    if proposal is not None:
                        healing.append(proposal)
            except Exception as e:  # driver errors, assertion failures, timeouts
                status, error = StepStatus.FAILED, f"{type(e).__name__}: {e}"

            if status is StepStatus.FAILED:
                failed = True
                shot = driver.screenshot(f"{test.id}-step{i}")
                if shot:
                    evidence.append(shot)
            results.append(
                StepResult(
                    index=i,
                    intent=step.intent,
                    status=status,
                    duration_ms=round((time.perf_counter() - start) * 1000, 2),
                    error=error,
                    evidence=evidence,
                )
            )
    finally:
        driver.close()

    return RunResult(test_id=test.id, environment=env.name, steps=results, healing=healing)


def _execute(step: Step, data: dict[str, str], runtime: dict[str, str], driver: Driver) -> Resolution | None:
    value = render_value(step.value, data, runtime)
    a = step.action

    if a is Action.NAVIGATE:
        driver.navigate(value)  # type: ignore[arg-type]
        return None
    if a is Action.WAIT_JOB:
        final = driver.wait_job(value, float(step.options.get("timeout_s", 900)))  # type: ignore[arg-type]
        expected = step.options.get("expect", "SUCCEEDED")
        if final != expected:
            raise StepFailure(f"job {value!r} ended {final}, expected {expected}")
        return None
    if a is Action.API_CALL:
        code = driver.api_call(value, step.options)  # type: ignore[arg-type]
        expected_code = int(step.options.get("expect_status", 200))
        if code != expected_code:
            raise StepFailure(f"API returned {code}, expected {expected_code}")
        return None

    assert step.target is not None  # guaranteed by Step validation
    res = resolve(step.target, driver)
    s, v = res.strategy, res.value
    if a is Action.CLICK:
        driver.click(s, v)
    elif a is Action.FILL:
        driver.fill(s, v, value)  # type: ignore[arg-type]
    elif a is Action.SELECT:
        driver.select(s, v, value)  # type: ignore[arg-type]
    elif a is Action.ASSERT_VISIBLE:
        pass  # resolving to exactly one element is the assertion
    elif a is Action.ASSERT_TEXT:
        actual = driver.text_of(s, v)
        if value is None or value not in actual:
            raise StepFailure(f"expected text {value!r}, found {actual!r}")
    return res
