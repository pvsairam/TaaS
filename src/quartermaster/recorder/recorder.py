"""Record a test by clicking through Fusion; save it as a replayable YAML spec.

Browser events (from capture.js) arrive as dicts. The conversion rules live in
`recorder.steps` and are pure, so they are unit-tested without a browser.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from quartermaster.domain.models import Priority, TestCase
from quartermaster.recorder.steps import events_to_steps

CAPTURE_JS = (Path(__file__).parent / "capture.js").read_text(encoding="utf-8")


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
    """Turn captured events into a test (conversion rules: `recorder.steps`)."""
    steps, data = events_to_steps(events)
    if not steps:
        raise ValueError("no usable actions were recorded")
    return TestCase.model_validate(
        {
            "id": test_id,
            "title": title,
            "module": module,
            "product": product,
            "persona": persona,
            "priority": priority,
            "tags": ["recorded"],
            "data": data,
            "steps": steps,
        }
    )


def to_yaml(test: TestCase) -> str:
    raw = test.model_dump(mode="json", exclude_defaults=True)
    for step in raw["steps"]:
        if "target" in step:
            step["target"]["strategies"] = [dict(s) for s in step["target"]["strategies"]]
    header = (
        "# Recorded with `qm record`. Review before committing:\n"
        "#  - rename data keys (value1, value2...) to meaningful names\n"
        "#  - make sure there is a check (assert_text / assert_visible) that proves the outcome;\n"
        "#    add them while recording with the Add check button\n"
    )
    return header + yaml.safe_dump(raw, sort_keys=False, allow_unicode=True)


class Recorder:
    """Attaches capture.js to a Playwright page and collects events.

    `stopped` turns true when the person presses Stop recording in the browser toolbar.
    """

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.stopped = False

    def _receive(self, payload: dict[str, Any]) -> None:
        if payload.get("kind") == "stop":
            self.stopped = True
        else:
            self.events.append(payload)

    def attach(self, page: Any) -> None:
        page.context.expose_binding("__qmRecord", lambda _source, payload: self._receive(payload))
        page.context.add_init_script(CAPTURE_JS)
        page.evaluate(CAPTURE_JS)  # current page too, not only future navigations
