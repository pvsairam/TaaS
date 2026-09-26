"""Turn recorded browser events into test steps, as plain data.

Pure and dependency-free, so the rules can be checked anywhere; `recorder.events_to_test`
wraps the result in the domain model. Events come from capture.js:

    click           {"kind": "click", "intent", "candidates"}
    fill / select   {..., "value"}; a select may carry "pick", the suggestion clicked in a
                    type-ahead list when it differs from what was typed
    navigate        {"kind": "navigate", "value": "My Client Groups > Workforce Structures"}
    assert_text     {..., "value"}: a check the person added while recording
    assert_visible  {...}: a check that the element is shown
"""

from __future__ import annotations

from typing import Any

_KINDS = {"click", "fill", "select", "navigate", "assert_text", "assert_visible"}
_VALUED = {"fill", "select", "assert_text"}
_STRATEGIES = {"label", "role", "test_id", "text", "css", "xpath"}


def _strategies(event: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {c["strategy"]: c["value"]}
        for c in event.get("candidates", [])
        if c.get("strategy") in _STRATEGIES and c.get("value")
    ]


def _key(event: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple((c.get("strategy", ""), c.get("value", "")) for c in event.get("candidates", []))


def events_to_steps(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Return (steps, data). Typed and checked values become data entries (value1, value2...)
    so they can be changed without touching the steps."""
    kept: list[dict[str, Any]] = []
    for ev in events:
        kind = ev.get("kind")
        if kind not in _KINDS:
            continue
        last = kept[-1] if kept else None
        # Editing the same field twice in a row keeps only the final value.
        if last and kind in ("fill", "select") and last["kind"] == kind and _key(last) == _key(ev):
            kept[-1] = ev
            continue
        if last and kind == "navigate" and last["kind"] == "navigate" and last.get("value") == ev.get("value"):
            continue
        kept.append(ev)

    steps: list[dict[str, Any]] = []
    data: dict[str, str] = {}
    for n, ev in enumerate(kept, 1):
        kind = ev["kind"]
        if kind == "navigate":
            path = str(ev.get("value") or "").strip()
            if path:
                steps.append({"action": "navigate", "intent": f"Open {path}", "value": path})
            continue
        strategies = _strategies(ev)
        if not strategies:
            continue  # nothing we can reliably find again
        name = ev.get("intent") or f"step {n}"
        step: dict[str, Any] = {"action": kind, "target": {"strategies": strategies}}
        if kind in _VALUED:
            key = f"value{len(data) + 1}"
            data[key] = str(ev.get("value", ""))
            step["value"] = f"${{{key}}}"
        if kind == "fill":
            step["intent"] = f"Enter {name}"
        elif kind == "select":
            step["intent"] = f"Choose {name}"
            pick = str(ev.get("pick") or "").strip()
            if pick and pick != str(ev.get("value", "")).strip():
                step["options"] = {"pick": pick}
        elif kind == "assert_text":
            step["intent"] = f"Check {name}"
        elif kind == "assert_visible":
            step["intent"] = f"Check {name} is shown"
        else:
            step["intent"] = f"Click {name}"
        steps.append(step)
    return steps, data
