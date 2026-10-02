"""Deterministic step executor.

The engine only knows the `Driver` protocol. `PlaywrightDriver` talks to a real Fusion pod;
tests use an in-memory fake. Business flows are sequential, so the first failed step skips
the rest.
"""

from __future__ import annotations

import sys
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol

from quartermaster.domain.models import (
    Action,
    Environment,
    HealingProposal,
    Locator,
    LocatorStrategy,
    RunResult,
    ScreenshotMode,
    Step,
    StepResult,
    StepStatus,
    TestCase,
)
from quartermaster.dsl.loader import display_value, render_value
from quartermaster.locators.resolver import Resolution, ResolutionError, resolve
from quartermaster.safety.guards import assert_safe_target


class Driver(Protocol):
    def open(self, env: Environment, persona: str) -> None: ...
    def login_as(self, persona: str) -> None: ...
    def close(self) -> None: ...
    def count(self, strategy: LocatorStrategy, value: str) -> int: ...
    def navigate(self, path: str) -> None: ...
    def click(self, strategy: LocatorStrategy, value: str) -> None: ...
    def fill(self, strategy: LocatorStrategy, value: str, text: str) -> None: ...
    def select(self, strategy: LocatorStrategy, value: str, option: str, pick: str | None = None) -> None: ...
    def text_of(self, strategy: LocatorStrategy, value: str) -> str: ...
    def wait_job(self, job_name: str, timeout_s: float) -> str: ...
    def api_call(self, request: str, options: dict[str, Any]) -> int: ...
    def screenshot(self, name: str, highlight: tuple[LocatorStrategy, str] | None = None) -> str | None: ...


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
    screenshots: ScreenshotMode = ScreenshotMode.ON_FAILURE,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> RunResult:
    """Run one test. `on_event`, if given, hears about progress as it happens (for live views):
    run_start, step_start, step_end and run_end, each a small JSON-ready dict."""
    assert_safe_target(env, allowed_hosts)
    run_id = run_id or uuid.uuid4().hex[:8].upper()

    def emit(kind: str, **fields: Any) -> None:
        if on_event is not None:
            on_event({"type": kind, "test_id": test.id, "run_id": run_id, "at": _now(), **fields})

    runtime = {"RUN_ID": run_id}
    results: list[StepResult] = []
    healing: list[HealingProposal] = []
    started_at = _now()

    emit("run_start", title=test.title, steps=len(test.steps))
    driver.open(env, test.persona)
    try:
        failed = False
        for i, step in enumerate(test.steps):
            base: dict[str, Any] = {
                "index": i,
                "intent": step.intent,
                "action": step.action.value,
                "value": display_value(step.value, test.data, runtime),  # masked values stay hidden
                "expected": step.expected,
            }
            if failed:
                results.append(StepResult(**base, status=StepStatus.SKIPPED))
                emit("step_end", index=i, intent=step.intent, status=StepStatus.SKIPPED.value, error=None, evidence=[])
                continue
            emit("step_start", index=i, intent=step.intent)
            start = time.perf_counter()
            step_started = _now()
            status, error, evidence = StepStatus.PASSED, None, []
            seen: dict[str, Resolution] = {}

            def before_click(res: Resolution, i: int = i, evidence: list[str] = evidence) -> None:
                # A picture just before a click, with the item about to be clicked boxed in red: the
                # one taken after it often shows a new page, where that item is gone.
                try:
                    shot = driver.screenshot(f"step-{i + 1:02d}-before", (res.strategy, res.value))
                except Exception:  # a busy page: the picture after the step still comes
                    return
                if shot:
                    evidence.append(shot)

            wants_before = step.action is Action.CLICK and screenshots is ScreenshotMode.EVERY_STEP
            try:
                res = _execute(step, test.data, runtime, driver, seen, before_click if wants_before else None)
                if res is not None and res.healed:
                    status = StepStatus.HEALED
                    healing.append(
                        HealingProposal(
                            step_index=i,
                            intent=step.intent,
                            # Template values (not rendered data), so the patch applies to the spec.
                            old=step.target.ordered()[0],  # type: ignore[union-attr]
                            new=step.target.ordered()[res.index],  # type: ignore[union-attr]
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

            used = seen.get("res")
            if status is StepStatus.FAILED:
                failed = True
            screenshot_note = None
            if _wants_screenshot(screenshots, status):
                # Taken after the step, with the element it used outlined when still on screen.
                try:
                    shot = driver.screenshot(f"step-{i + 1:02d}", (used.strategy, used.value) if used else None)
                except Exception as e:  # a page too busy to capture must not end the run; the step keeps its result
                    shot = None
                    screenshot_note = "The screen could not be captured: the page was still loading."
                    print(
                        f"warning: step {i + 1}: no screenshot ({type(e).__name__}: {e})".splitlines()[0],
                        file=sys.stderr,
                    )
                if shot:
                    evidence.append(shot)
            results.append(
                StepResult(
                    **base,
                    status=status,
                    duration_ms=round((time.perf_counter() - start) * 1000, 2),
                    error=error,
                    evidence=evidence,
                    locator=f"{used.strategy.value}={used.value}" if used else None,
                    started_at=step_started,
                    screenshot_note=screenshot_note,
                )
            )
            emit("step_end", index=i, intent=step.intent, status=status.value, error=error, evidence=evidence)
    finally:
        driver.close()

    result = RunResult(
        test_id=test.id,
        environment=env.name,
        steps=results,
        healing=healing,
        run_id=run_id,
        test_title=test.title,
        persona=test.persona,
        environment_url=env.url,
        release=env.release,
        started_at=started_at,
        finished_at=_now(),
        screenshots=screenshots,
    )
    emit("run_end", status=result.status.value)
    return result


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _wants_screenshot(mode: ScreenshotMode, status: StepStatus) -> bool:
    if mode is ScreenshotMode.EVERY_STEP:
        return True
    return mode is ScreenshotMode.ON_FAILURE and status is StepStatus.FAILED


def _execute(
    step: Step,
    data: dict[str, str],
    runtime: dict[str, str],
    driver: Driver,
    seen: dict[str, Resolution],
    before_click: Callable[[Resolution], None] | None = None,
) -> Resolution | None:
    value = render_value(step.value, data, runtime)
    a = step.action

    if a is Action.LOGIN_AS:
        driver.login_as(value)  # type: ignore[arg-type]
        return None
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
    target = Locator(
        strategies=[{s: render_value(v, data, runtime) or v} for s, v in step.target.ordered()],
        description=step.target.description,
    )
    res = resolve(target, driver)
    seen["res"] = res  # kept even if the action below fails, for the report and screenshot
    s, v = res.strategy, res.value
    if a is Action.CLICK:
        if before_click is not None:
            before_click(res)
        driver.click(s, v)
    elif a is Action.FILL:
        driver.fill(s, v, value)  # type: ignore[arg-type]
    elif a is Action.SELECT:
        # `pick`: the suggestion to choose when it differs from the text typed (e.g. from a recording).
        pick = render_value(step.options.get("pick"), data, runtime)
        driver.select(s, v, value, pick=pick)  # type: ignore[arg-type]
    elif a is Action.ASSERT_VISIBLE:
        pass  # resolving to exactly one element is the assertion
    elif a is Action.ASSERT_TEXT:
        actual = driver.text_of(s, v)
        # Oracle pages pad text with tabs and line breaks, so compare with whitespace collapsed.
        if value is None or " ".join(value.split()) not in " ".join(actual.split()):
            raise StepFailure(f"expected text {value!r}, found {actual!r}")
    return res
