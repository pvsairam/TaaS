"""Record a test by clicking through Fusion; save it as a replayable YAML spec.

Browser events (from capture.js) arrive as dicts. `events_to_test` is pure, so the
conversion rules are unit-tested without a browser.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from quartermaster.domain.models import Action, Locator, LocatorStrategy, Priority, Step, TestCase

CAPTURE_JS = (Path(__file__).parent / "capture.js").read_text(encoding="utf-8")

_ACTIONS = {"click": Action.CLICK, "fill": Action.FILL, "select": Action.SELECT}
_VALID_STRATEGIES = {s.value for s in LocatorStrategy}


def _locator(event: dict[str, Any]) -> Locator | None:
    strategies = [
        {LocatorStrategy(c["strategy"]): c["value"]}
        for c in event.get("candidates", [])
        if c.get("strategy") in _VALID_STRATEGIES and c.get("value")
    ]
    return Locator(strategies=strategies, description=event.get("intent", "")) if strategies else None


def _key(event: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple((c["strategy"], c["value"]) for c in event.get("candidates", []))


def events_to_test(
    events: list[dict[str, Any]],
    *,
    test_id: str,
    title: str,
    module: str,
    product: str,
    persona: str = "",
    priority: Priority = Priority.MEDIUM,
) -> TestCase:
    """Turn captured events into a test. Repeated edits of one field keep only the last value,
    and typed values become `data` entries so they can be changed without touching steps."""
    kept: list[dict[str, Any]] = []
    for ev in events:
        if ev.get("kind") not in _ACTIONS:
            continue
        if ev["kind"] in ("fill", "select") and kept and kept[-1]["kind"] == ev["kind"] and _key(kept[-1]) == _key(ev):
            kept[-1] = ev
            continue
        kept.append(ev)

    steps: list[Step] = []
    data: dict[str, str] = {}
    for n, ev in enumerate(kept, 1):
        target = _locator(ev)
        if target is None:
            continue  # nothing we can reliably find again
        intent = ev.get("intent") or f"Step {n}"
        value = None
        if ev["kind"] in ("fill", "select"):
            name = f"value{len(data) + 1}"
            data[name] = str(ev.get("value", ""))
            value = f"${{{name}}}"
            intent = f"{'Enter' if ev['kind'] == 'fill' else 'Choose'} {intent}"
        else:
            intent = f"Click {intent}"
        steps.append(Step(action=_ACTIONS[ev["kind"]], intent=intent, target=target, value=value))

    if not steps:
        raise ValueError("no usable actions were recorded")
    return TestCase(
        id=test_id,
        title=title,
        module=module,
        product=product,
        persona=persona,
        priority=priority,
        tags=["recorded"],
        data=data,
        steps=steps,
    )


def to_yaml(test: TestCase) -> str:
    raw = test.model_dump(mode="json", exclude_defaults=True)
    for step in raw["steps"]:
        if "target" in step:
            step["target"]["strategies"] = [dict(s) for s in step["target"]["strategies"]]
    header = (
        "# Recorded with `qm record`. Review before committing:\n"
        "#  - rename data keys (value1, value2...) to meaningful names\n"
        "#  - add an assert_visible / assert_text step that proves the outcome\n"
    )
    return header + yaml.safe_dump(raw, sort_keys=False, allow_unicode=True)


class Recorder:
    """Attaches capture.js to a Playwright page and collects events."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def attach(self, page: Any) -> None:
        page.context.expose_binding("__qmRecord", lambda _source, payload: self.events.append(payload))
        page.context.add_init_script(CAPTURE_JS)
        page.evaluate(CAPTURE_JS)  # current page too, not only future navigations
