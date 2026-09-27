from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from quartermaster.domain.models import Action, Environment, EnvironmentKind, LocatorStrategy, StepStatus
from quartermaster.dsl.loader import load_test
from quartermaster.recorder.recorder import events_to_test, to_yaml

META = dict(test_id="hcm.recorded", title="Recorded", module="HCM", product="Global Human Resources")


def _ev(kind: str, intent: str, *cands: tuple[str, str], value: str | None = None) -> dict[str, Any]:
    ev: dict[str, Any] = {"kind": kind, "intent": intent, "candidates": [{"strategy": s, "value": v} for s, v in cands]}
    if value is not None:
        ev["value"] = value
    return ev


def test_events_become_steps_with_data() -> None:
    events = [
        _ev("fill", "Person Number", ("label", "Person Number"), value="1"),
        _ev("fill", "Person Number", ("label", "Person Number"), value="10"),  # re-edit: keep last
        _ev("click", "Search", ("role", "button:Search"), ("text", "Search")),
    ]
    test = events_to_test(events, **META)
    assert [s.action for s in test.steps] == [Action.FILL, Action.CLICK]
    assert test.data == {"value1": "10"}
    assert test.steps[0].value == "${value1}"
    assert test.steps[1].target is not None
    assert test.steps[1].target.ordered() == [(LocatorStrategy.ROLE, "button:Search"), (LocatorStrategy.TEXT, "Search")]


def test_events_without_locators_or_unknown_kinds_are_dropped() -> None:
    events = [
        _ev("click", "icon"),
        {"kind": "scroll"},
        _ev("click", "Save", ("bogus", "x"), ("text", "Save")),
    ]
    test = events_to_test(events, **META)
    assert len(test.steps) == 1
    assert test.steps[0].target is not None
    assert test.steps[0].target.ordered() == [(LocatorStrategy.TEXT, "Save")]


def test_nothing_recorded_is_an_error() -> None:
    with pytest.raises(ValueError, match="no usable actions"):
        events_to_test([], **META)


def test_recorded_pick_round_trips_and_is_used_on_replay(tmp_path: Path) -> None:
    from conftest import FakeDriver

    from quartermaster.runner.engine import run_test

    events = [
        {"kind": "navigate", "value": "My Client Groups > Workforce Structures"},
        _ev("select", "Postal Code", ("role", "combobox:Postal Code"), value="94065"),
        {**_ev("assert_text", "City", ("label", "City"), value="Redwood Shores")},
    ]
    events[1]["pick"] = "94065 Redwood Shores, San Mateo, CA"
    test = events_to_test(events, **META)
    p = tmp_path / "t.yaml"
    p.write_text(to_yaml(test))
    saved = load_test(p)
    assert [s.action for s in saved.steps] == [Action.NAVIGATE, Action.SELECT, Action.ASSERT_TEXT]
    assert saved.steps[1].options == {"pick": "94065 Redwood Shores, San Mateo, CA"}

    env = Environment(name="t", url="https://abcd-test.fa.us2.oraclecloud.com", kind=EnvironmentKind.TEST)
    d = FakeDriver({("role", "combobox:Postal Code"): 1, ("label", "City"): 1}, texts={"City": " Redwood\tShores "})
    result = run_test(saved, env, d)
    assert result.status is StepStatus.PASSED, [s.error for s in result.steps]  # whitespace is collapsed
    assert ("navigate", "My Client Groups > Workforce Structures") in d.calls
    assert ("select", "role", "combobox:Postal Code", "94065", "94065 Redwood Shores, San Mateo, CA") in d.calls


def test_stop_from_the_browser_ends_recording_without_a_step() -> None:
    from quartermaster.recorder.recorder import Recorder

    r = Recorder()
    r._receive(_ev("click", "Save", ("role", "button:Save")))
    r._receive({"kind": "stop"})
    assert r.stopped and [e["kind"] for e in r.events] == ["click"]


def test_yaml_round_trip(tmp_path: Path) -> None:
    test = events_to_test([_ev("select", "Legal Employer", ("label", "Legal Employer"), value="US1")], **META)
    p = tmp_path / "t.yaml"
    p.write_text(to_yaml(test))
    assert p.read_text().startswith("# Recorded with `qm record`")
    assert load_test(p) == test


# ------------------------------------------------------------------ real browser, end to end

_PREINSTALLED = Path("/opt/pw-browsers/chromium")
# A pinned Chromium if there is one; otherwise Playwright's own (`python -m playwright install chromium`).
CHROMIUM = os.environ.get("QM_CHROMIUM_PATH") or (str(_PREINSTALLED) if _PREINSTALLED.exists() else "")
MOCK = (Path(__file__).parent / "fixtures" / "mock_fusion.html").read_text()
POD = "https://mock-dev1.fa.us1.oraclecloud.com/"


def _serve_mock(context: Any) -> None:
    context.route("**/*", lambda route: route.fulfill(status=200, content_type="text/html", body=MOCK))


def test_record_then_replay_in_real_browser(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from quartermaster.recorder.recorder import Recorder
    from quartermaster.runner.engine import run_test
    from quartermaster.runner.playwright_driver import PlaywrightDriver

    environ = {"QM_FUSION_USER": "Mock User", "QM_FUSION_PASSWORD": "not-a-real-secret"}
    if CHROMIUM:
        environ["QM_CHROMIUM_PATH"] = CHROMIUM
    env = Environment(name="mock", url=POD, kind=EnvironmentKind.DEV)

    # Record: a person drives the browser (simulated here with Playwright input events).
    rec_driver = PlaywrightDriver(evidence_dir=str(tmp_path), environ=environ, context_hook=_serve_mock)
    rec_driver.open(env, "")
    try:
        recorder = Recorder()
        recorder.attach(rec_driver.page)
        page = rec_driver.page
        page.get_by_label("Person Number").fill("10")
        page.get_by_label("Legal Employer").select_option(label="US1 Legal Entity")
        page.get_by_role("button", name="Search").click()
        page.wait_for_timeout(200)
    finally:
        rec_driver.close()

    test = events_to_test(recorder.events, **META)
    out = tmp_path / "recorded.yaml"
    out.write_text(to_yaml(test))
    saved = load_test(out)

    # Generated ADF ids must never be used as locators, and the password is never captured.
    text = out.read_text()
    assert "pt1:" not in text and "not-a-real-secret" not in text
    assert saved.data == {"value1": "10", "value2": "US1 Legal Entity"}
    assert [s.action for s in saved.steps] == [Action.FILL, Action.SELECT, Action.CLICK]

    # Replay the saved file with a fresh browser.
    play_driver = PlaywrightDriver(evidence_dir=str(tmp_path), environ=environ, context_hook=_serve_mock)
    result = run_test(saved, env, play_driver)
    assert result.status is StepStatus.PASSED, [s.error for s in result.steps]


def test_commands_while_recording(tmp_path: Path) -> None:
    import json

    from quartermaster.recorder.recorder import Recorder

    feed = tmp_path / "feed.json"
    r = Recorder(feed=feed, test_id="hcm.view-worker")
    r.command("note too early")
    assert "Record a step first" in r.message
    r._receive(_ev("fill", "PIN", ("label", "PIN"), value="1234"))
    r.command("mask")
    r.command("note   The PIN is accepted")
    r.command("pause")
    r._receive(_ev("click", "Ignored while paused", ("role", "button:X")))
    r.command("resume")
    r._receive(_ev("click", "Save", ("role", "button:Save")))
    r.command("undo")
    shown = json.loads(feed.read_text(encoding="utf-8"))
    assert [s["intent"] for s in shown["steps"]] == ["Enter PIN"]
    assert shown["steps"][0] == {**shown["steps"][0], "value": "••••••", "expected": "The PIN is accepted"}
    assert shown["paused"] is False and shown["masked"] == 1 and "1234" not in feed.read_text(encoding="utf-8")
    test = events_to_test(r.events, **{**META, "test_id": "hcm.view-worker"})
    assert test.data == {"secret1": "${env:QM_HCM_VIEW_WORKER_1}"}
    text = to_yaml(test)
    assert "QM_HCM_VIEW_WORKER_1" in text and "1234" not in text
    r.command("stop")
    assert r.stopped
