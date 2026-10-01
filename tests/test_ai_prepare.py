"""Preparing a manual scenario with an AI: any provider, the safety rules, and a real browser run.
No real AI is called: a local stand-in server answers like the providers do, or a scripted 'AI'."""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
from test_guided import PAGE, SCENARIO, FakePage
from test_recorder import CHROMIUM, POD

from quartermaster.ai import providers
from quartermaster.ai.providers import AIConfig, AIError, chat, check_settings, config_from, parse_json
from quartermaster.domain.models import Environment, EnvironmentKind, StepStatus
from quartermaster.dsl.loader import load_test
from quartermaster.recorder.autopilot import Autopilot
from quartermaster.recorder.guided import Guide
from quartermaster.recorder.recorder import Recorder

# ---------------------------------------------------------------------- providers


class FakeProvider(BaseHTTPRequestHandler):
    seen: list[dict[str, Any]] = []

    def do_POST(self) -> None:  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeProvider.seen.append(
            {"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body}
        )
        if self.headers.get("x-api-key") == "bad" or self.headers.get("Authorization") == "Bearer bad":
            self.send_response(401)
            self.end_headers()
            return
        if self.path.endswith("/messages"):
            reply = {"content": [{"type": "text", "text": "OK from claude"}]}
        else:
            reply = {"choices": [{"message": {"content": "OK from " + body["model"]}}]}
        data = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture
def server() -> Iterator[str]:
    srv = HTTPServer(("127.0.0.1", 0), FakeProvider)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    FakeProvider.seen.clear()
    yield f"http://127.0.0.1:{srv.server_address[1]}/v1"
    srv.shutdown()


def test_any_openai_compatible_provider_and_anthropic(server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_KEY", "secret-key")
    openai_like = AIConfig("openrouter", "some/model", server, "MY_KEY")
    assert chat(openai_like, "sys", "Mail jane@example.com, card 4111 1111 1111 1111") == "OK from some/model"
    sent = FakeProvider.seen[-1]
    assert sent["path"] == "/v1/chat/completions" and sent["headers"]["authorization"] == "Bearer secret-key"
    user = sent["body"]["messages"][1]["content"]
    assert "jane@example.com" not in user and "4111" not in user  # masked before it leaves this computer

    claude = AIConfig("anthropic", "claude-sonnet-5-5", server, "MY_KEY")
    assert chat(claude, "sys", "hello") == "OK from claude"
    assert (
        FakeProvider.seen[-1]["path"] == "/v1/messages"
        and FakeProvider.seen[-1]["headers"]["x-api-key"] == "secret-key"
    )

    local = AIConfig("ollama", "llama", server, "")  # no key needed
    assert chat(local, "sys", "hi") == "OK from llama" and "authorization" not in FakeProvider.seen[-1]["headers"]

    monkeypatch.setenv("MY_KEY", "bad")
    with pytest.raises(AIError, match="refused the key"):
        chat(openai_like, "sys", "hi")
    assert providers.check(openai_like)["ok"] is False


def test_settings_choose_a_provider_but_never_store_a_key() -> None:
    assert config_from({"ai_provider": "anthropic"}).model == "claude-sonnet-5-5"
    gemini = config_from({"ai_provider": "gemini", "ai_model": "my-model"})
    assert (
        gemini.base_url.startswith("https://generativelanguage.googleapis.com") and gemini.key_env == "GEMINI_API_KEY"
    )
    assert "GEMINI_API_KEY" in gemini.problem({})
    assert gemini.problem({"GEMINI_API_KEY": "k"}) == ""
    assert "model" in config_from({"ai_provider": "openai"}).problem({"OPENAI_API_KEY": "k"})
    assert config_from({"ai_provider": "ollama", "ai_model": "llama"}).problem({}) == ""
    assert "https" in AIConfig("custom", "m", "ftp://x", "").problem({})
    with pytest.raises(ValueError, match="NAME of an environment variable"):
        check_settings({"ai_key_env": "sk-123 my key"})
    with pytest.raises(ValueError, match="unknown AI provider"):
        check_settings({"ai_provider": "skynet"})
    assert parse_json('Sure!\n```json\n{"do": "done", "why": "ok"}\n```') == {"do": "done", "why": "ok"}
    with pytest.raises(AIError):
        parse_json("no json here")


def test_settings_api_and_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from test_service_api import call

    from quartermaster.service.api import App

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    (tmp_path / "tests").mkdir()
    app = App(tests_root=tmp_path / "tests", evidence_root=tmp_path / "ev", data_dir=tmp_path / ".qm")
    ai = call(app, "GET", "/api/status")["ai"]
    assert ai["provider"] == "" and "No AI" in ai["problem"] and len(ai["presets"]) >= 8
    call(app, "POST", "/api/settings", {"ai_provider": "deepseek", "ai_model": "deepseek-chat"})
    ai = call(app, "GET", "/api/status")["ai"]
    assert (ai["key_env"], ai["key_set"]) == ("DEEPSEEK_API_KEY", False) and "DEEPSEEK_API_KEY" in ai["problem"]
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-very-secret-123")
    ai = call(app, "GET", "/api/status")["ai"]
    assert ai["key_set"] is True and ai["problem"] == ""
    assert "sk-very-secret-123" not in json.dumps(call(app, "GET", "/api/status"))
    assert "sk-very-secret-123" not in (tmp_path / ".qm" / "settings.json").read_text()


# ---------------------------------------------------------------------- the AI loop (no browser)


class Locator:
    def __init__(self, page: ScriptedPage, key: str) -> None:
        self.page, self.key = page, key

    def count(self) -> int:
        return self.page.counts.get(self.key, 0)

    @property
    def first(self) -> Locator:
        return self

    def click(self, timeout: float) -> None:
        self.page.done.append(("click", self.key))
        self.page.screen = self.page.after.get(self.key, self.page.screen)

    def fill(self, value: str, timeout: float) -> None:
        self.page.done.append(("fill", self.key, value))


class ScriptedPage(FakePage):
    def __init__(self, screens: dict[str, dict[str, Any]], start: str, counts: dict[str, int]) -> None:
        super().__init__()
        self.screens, self.screen, self.counts = screens, start, counts
        self.after = {f"role:link:{n}": n for n in screens}
        self.done: list[tuple[str, ...]] = []

    def evaluate(self, script: str) -> dict[str, Any]:
        return self.screens[self.screen]

    def get_by_role(self, role: str, name: str, exact: bool) -> Locator:
        return Locator(self, f"role:{role}:{name}")

    def get_by_text(self, text: str, exact: bool) -> Locator:
        return Locator(self, f"text:{text}")

    def get_by_label(self, text: str, exact: bool) -> Locator:
        return Locator(self, f"label:{text}")


def screen(*links: str, texts: tuple[str, ...] = ()) -> dict[str, Any]:
    return {"title": "", "headings": [], "items": [{"role": "link", "name": n} for n in links], "texts": list(texts)}


def scripted_ai(answers: list[dict[str, Any]]) -> Any:
    prompts: list[str] = []

    def ask(system: str, prompt: str) -> str:
        prompts.append(prompt)
        return json.dumps(answers.pop(0))

    ask.prompts = prompts  # type: ignore[attr-defined]
    return ask


def test_the_ai_does_each_step_and_adds_checks(tmp_path: Path) -> None:
    screens = {
        "home": screen("Me", "Delete"),
        "Me": screen("Personal Information"),
        "Personal Information": screen("My Compensation"),
        "My Compensation": screen("Me", texts=("My Compensation", "Current Salary")),
    }
    counts = {f"role:link:{n}": 1 for n in screens} | {"text:Current Salary": 1}
    page = ScriptedPage(screens, "home", counts)
    recorder = Recorder(test_id="t")
    guide = Guide(SCENARIO, tmp_path / "run")
    ask = scripted_ai(
        [
            {"do": "done", "why": "already signed in"},
            {"do": "click", "element": 1},
            {"do": "done"},
            {"do": "click", "element": 1},
            {"do": "done"},
            {"do": "click", "element": 1},
            {"do": "done"},
            {"check": [2]},
        ]
    )
    assert Autopilot(page, guide, recorder, ask).run() is True
    assert [d[1] for d in page.done] == ["role:link:Me", "role:link:Personal Information", "role:link:My Compensation"]
    assert [e["kind"] for e in recorder.events] == ["click", "click", "click", "assert_visible"]
    assert recorder.events[0]["candidates"][0] == {"strategy": "role", "value": "link:Me"}
    assert recorder.events[-1]["candidates"] == [{"strategy": "text", "value": "Current Salary"}]
    assert all(s["status"] == "passed" and s["picture"] for s in guide.state())
    assert '[1] link "Me"' in ask.prompts[0] and "Step 1 of 4: Login" in ask.prompts[0]


@pytest.mark.parametrize(
    ("answers", "why"),
    [
        ([{"do": "done"}, {"do": "click", "element": 2}], 'click "Delete", which can change data'),
        ([{"do": "done"}, {"do": "fill", "element": 1, "value": "12345"}], "does not give the value"),
        ([{"do": "done"}, {"do": "click", "element": 9}], "not on the screen"),
        ([{"do": "done"}, {"do": "stuck", "why": "needs a supplier name"}], "needs a supplier name"),
        ([{"do": "done"}] + [{"do": "click", "element": 1}] * 5, "not finished after 5 actions"),
    ],
)
def test_the_ai_stops_rather_than_guess(tmp_path: Path, answers: list[dict[str, Any]], why: str) -> None:
    page = ScriptedPage({"home": screen("Me", "Delete")}, "home", {"role:link:Me": 1, "role:link:Delete": 1})
    page.after = {}  # clicking changes nothing, so the step never completes
    guide = Guide(SCENARIO, tmp_path / "run")
    pilot = Autopilot(page, guide, Recorder(test_id="t"), scripted_ai(answers))
    assert pilot.run() is False and why in pilot.reason
    marks = guide.state()
    assert marks[0]["status"] == "passed" and marks[1]["status"] == "failed" and "status" not in marks[2]
    result = guide.result(test_id="t", title="x", environment="e", environment_url=POD, release=None, run_id="r")
    assert result.status is StepStatus.FAILED


def test_stop_from_the_web_page(tmp_path: Path) -> None:
    page = ScriptedPage({"home": screen("Me")}, "home", {"role:link:Me": 1})
    pilot = Autopilot(
        page, Guide(SCENARIO, tmp_path / "r"), Recorder(test_id="t"), scripted_ai([]), should_stop=lambda: True
    )
    assert pilot.run() is False and "stopped by the tester" in pilot.reason


def test_prepare_saves_a_draft_only_when_every_step_was_done(tmp_path: Path) -> None:
    import argparse

    from quartermaster.cli import _finish_by_hand

    evidence = tmp_path / "ev"
    env = Environment(name="f", url=POD, kind=EnvironmentKind.DEV)

    def args(name: str) -> argparse.Namespace:
        return argparse.Namespace(
            id="manual.x.ess-001",
            title="My Compensation",
            module="HCM",
            product="GHR",
            persona="",
            process="",
            release="26C",
            tester="AI (OpenAI, m)",
            out=str(tmp_path / f"{name}.yaml"),
            evidence=str(evidence),
        )

    rec = Recorder(test_id="manual.x.ess-001")
    rec.guide = Guide(SCENARIO, evidence / "manual.x.ess-001" / "r1")
    rec.guide.mark("1 pass", FakePage())
    rec.guide.mark("2 fail The AI could not do this step: x", FakePage())
    rec.events.append({"kind": "click", "intent": "Me", "candidates": [{"strategy": "text", "value": "Me"}]})
    assert _finish_by_hand(args("partial"), rec, env, "r1", mode="ai", save_test=False) == 0
    assert not (tmp_path / "partial.yaml").exists()
    record = json.loads((evidence / "manual.x.ess-001" / "r1" / "run.json").read_text())
    assert record["mode"] == "ai" and record["status"] == "failed" and record["executed_by"].startswith("AI")


# ---------------------------------------------------------------------- a real browser


def browser_ai(system: str, prompt: str) -> str:
    """A scripted stand-in for an AI that reads the screen like a real one would."""
    if '"check"' in system:
        texts = re.findall(r"^\[(\d+)\] (.+)$", prompt, re.M)
        return json.dumps({"check": [int(n) for n, t in texts if t == "Current Salary"]})
    step = re.search(r"^Step \d+ of \d+: (.+)$", prompt, re.M).group(1)  # type: ignore[union-attr]
    if step == "Login" or "nothing yet" not in prompt:
        return json.dumps({"do": "done"})
    wanted = step.removeprefix("Select ").strip()
    for n, _role, name in re.findall(r'^\[(\d+)\] (\w+) "(.+)"$', prompt, re.M):
        if name == wanted:
            return json.dumps({"do": "click", "element": int(n), "why": f"the step says {wanted}"})
    return json.dumps({"do": "stuck", "why": "not on the screen"})


def test_prepared_in_a_real_browser_then_it_plays_by_itself(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from quartermaster.recorder.recorder import events_to_test, to_yaml
    from quartermaster.runner.engine import run_test
    from quartermaster.runner.playwright_driver import PlaywrightDriver

    environ = {"QM_FUSION_USER": "Mock User", "QM_FUSION_PASSWORD": "not-a-real-secret"}
    if CHROMIUM:
        environ["QM_CHROMIUM_PATH"] = CHROMIUM
    env = Environment(name="mock", url=POD, kind=EnvironmentKind.DEV)

    def serve(context: Any) -> None:
        context.route("**/*", lambda route: route.fulfill(status=200, content_type="text/html", body=PAGE))

    driver = PlaywrightDriver(evidence_dir=str(tmp_path), environ=environ, context_hook=serve)
    driver.open(env, "")
    recorder = Recorder(test_id="manual.ess.ess-001")
    recorder.guide = Guide(SCENARIO, tmp_path / "run")
    try:
        assert Autopilot(driver.page, recorder.guide, recorder, browser_ai, settle=driver._settle).run() is True
    finally:
        driver.close()

    assert all(s["status"] == "passed" and s["picture"] for s in recorder.guide.state())
    test = events_to_test(
        recorder.events,
        test_id="manual.ess.ess-001",
        title="My Compensation",
        module="HCM",
        product="Global Human Resources",
    )
    out = tmp_path / "ess-001.yaml"
    out.write_text(to_yaml(test))
    saved = load_test(out)
    assert [s.action.value for s in saved.steps] == ["click", "click", "click", "assert_visible"]
    assert "not-a-real-secret" not in out.read_text()

    play = PlaywrightDriver(evidence_dir=str(tmp_path), environ=environ, context_hook=serve)
    result = run_test(saved, env, play)
    assert result.status is StepStatus.PASSED, [s.error for s in result.steps]
