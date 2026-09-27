"""The local web service: API, recording and the HTTP guards. Stand-ins play `qm run` and `qm record`."""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from test_evidence_suite import _suite
from test_service_queue import fake_command

from quartermaster.evidence.suite import suite_folder, write_suite_document, write_suite_record
from quartermaster.service.api import ApiError, App, make_server, port_of

# Stand-in for `qm record`: waits for Enter (the web UI's Stop button), then saves a test file.
FAKE_RECORD = r"""
import os, sys
out = sys.argv[1]
if out.endswith('no_pod.yaml'):
    print('error: set QM_FUSION_URL to the non-prod pod URL'); sys.exit(2)
sys.stdin.readline()
os.makedirs(os.path.dirname(out), exist_ok=True)
open(out, 'w').write('id: x\ntitle: Recorded\nsteps: []\n')
print('Saved 0 step(s) to ' + out + '. Replay with: qm run ' + out)
"""


def fake_record(out: Path, fields: dict[str, str], evidence_root: Path) -> list[str]:
    return [sys.executable, "-c", FAKE_RECORD, str(out)]


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[App]:
    monkeypatch.setenv("QM_FUSION_URL", "https://abcd-dev2.fa.us6.oraclecloud.com")
    monkeypatch.setenv("QM_FUSION_USER", "tester")
    monkeypatch.setenv("QM_FUSION_PASSWORD", "secret")
    tests = tmp_path / "tests"
    (tests / "hcm").mkdir(parents=True)
    (tests / "hcm" / "pass.yaml").write_text("id: hcm.pass\ntitle: A passing test\nmodule: HCM\nsteps: [{}, {}]\n")
    (tests / "broken.yaml").write_text("id: [unclosed\n")
    a = App(
        tests_root=tests,
        evidence_root=tmp_path / "evidence",
        data_dir=tmp_path / ".qm",
        run_command=fake_command,
        record_command=fake_record,
    )
    a.start()
    yield a
    a.stop()


def call(app: App, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    reply = app.handle(method, path, json.dumps(body).encode() if body is not None else b"")
    return json.loads(reply.body)


def wait(check: Any, timeout: float = 20) -> Any:
    end = time.time() + timeout
    while time.time() < end:
        value = check()
        if value:
            return value
        time.sleep(0.1)
    raise AssertionError("timed out")


def test_status_never_shows_the_password(app: App) -> None:
    status = call(app, "GET", "/api/status")
    assert status["ready"] and status["user"] == "tester" and status["password_set"] is True
    assert "secret" not in json.dumps(status)


def test_tests_are_listed_with_their_last_result(app: App) -> None:
    tests = {t["file"]: t for t in call(app, "GET", "/api/tests")}
    assert tests["hcm/pass.yaml"]["title"] == "A passing test" and tests["hcm/pass.yaml"]["steps"] == 2
    assert tests["hcm/pass.yaml"]["folder"] == "hcm" and tests["hcm/pass.yaml"]["last_run"] is None
    assert "Could not read this file" in tests["broken.yaml"]["problem"]

    run = call(app, "POST", "/api/runs", {"target": "hcm/pass.yaml"})
    wait(lambda: call(app, "GET", f"/api/runs/{run['id']}")["status"] == "passed")
    tests = {t["file"]: t for t in call(app, "GET", "/api/tests")}
    assert tests["hcm/pass.yaml"]["last_run"]["status"] == "passed"


def test_a_run_can_be_started_and_followed(app: App) -> None:
    run = call(app, "POST", "/api/runs", {"target": "hcm/pass.yaml", "options": {"tester": "Sai"}})
    assert run["status"] == "queued" and run["options"]["tester"] == "Sai"
    assert "events_path" not in run and "log_path" not in run  # server paths stay on the server
    done = wait(lambda: (r := call(app, "GET", f"/api/runs/{run['id']}"))["status"] == "passed" and r)
    assert [e["type"] for e in done["events"]][0] == "suite_start"
    assert call(app, "GET", f"/api/runs/{run['id']}/events?after=2") == done["events"][2:]
    assert [r["id"] for r in call(app, "GET", "/api/runs")] == [run["id"]]


def test_bad_requests_get_a_plain_answer(app: App) -> None:
    for body, message in (
        ({"target": "../outside.yaml"}, "inside the tests folder"),
        ({"target": "hcm/pass.yaml", "options": {"shell": "x"}}, "unknown run options"),
    ):
        with pytest.raises(ApiError, match=message):
            call(app, "POST", "/api/runs", body)
    with pytest.raises(ApiError, match="no such run"):
        call(app, "GET", "/api/runs/nope")
    with pytest.raises(ApiError, match="not valid JSON"):
        app.handle("POST", "/api/runs", b"{nope")


def test_finished_run_links_to_its_evidence_in_plain_words(app: App) -> None:
    root = app.evidence_root
    suite = _suite(root)  # three tests: passed, failed at step 2, healed
    folder = suite_folder(root, "S1")
    write_suite_record(suite, folder)
    summary = write_suite_document(suite, root, folder / "summary.docx")
    run = app.queue.store.create("hcm", {"screenshots": "every-step", "video": "off"})
    app.queue.store.update(run["id"], status="failed", suite_dir=str(folder), summary=str(summary))

    detail = call(app, "GET", f"/api/runs/{run['id']}")
    assert detail["summary_url"] == "/files/_suites/S1/summary.docx" and detail["suite_folder"] == "_suites/S1"
    ok, failed, healed = detail["results"]
    assert ok["document_url"].endswith("hcm.view-worker_evidence.docx") and ok["folder"].startswith("hcm.view-worker/")
    assert failed["failed_step"]["error"] == 'The screen showed "Redwood City" but it should show "Redwood Shores".'
    assert failed["failed_step"]["detail"].startswith("StepFailure")
    assert healed["needs_update"] and not ok["needs_update"]

    picture = app.handle("GET", failed["failed_step"]["picture_url"], b"")
    assert picture.content_type == "image/png" and picture.body.startswith(b"\x89PNG")
    doc = app.handle("GET", detail["summary_url"], b"")
    assert doc.download_name == "summary.docx" and doc.body.startswith(b"PK")


def test_only_evidence_files_can_be_fetched_or_opened(app: App, tmp_path: Path) -> None:
    (tmp_path / "secret.txt").write_text("no")
    for path in ("/files/../secret.txt", "/files/..%2Fsecret.txt", "/files/%2E%2E/secret.txt"):
        with pytest.raises(ApiError, match="only files in the evidence folder"):
            app.handle("GET", path, b"")
    with pytest.raises(ApiError, match="only files in the evidence folder"):
        call(app, "POST", "/api/open", {"path": str(tmp_path)})


def test_recording_starts_stops_and_saves(app: App) -> None:
    request = {"id": "hcm.search-worker", "title": "Search", "module": "HCM", "product": "Global HR"}
    state = call(app, "POST", "/api/recording", request)
    assert state["status"] == "recording" and state["file"] == "recorded/hcm_search-worker.yaml"
    with pytest.raises(ApiError, match="already in progress"):
        call(app, "POST", "/api/recording", {**request, "id": "hcm.other"})

    call(app, "POST", "/api/recording/stop", {})
    saved = wait(lambda: (s := call(app, "GET", "/api/recording"))["status"] == "saved" and s)
    assert saved["message"].startswith("Saved 0 step(s)")
    assert (app.tests_root / "recorded" / "hcm_search-worker.yaml").is_file()

    with pytest.raises(ApiError, match="already exists"):  # never overwrite a test
        call(app, "POST", "/api/recording", request)


def test_recording_requests_are_checked_and_failures_explained(app: App) -> None:
    base = {"id": "hcm.x", "title": "T", "module": "HCM", "product": "P"}
    for change, message in (
        ({"title": ""}, "title is required"),
        ({"id": "Has Spaces"}, "id may use lower-case"),
        ({"file": "../../elsewhere.yaml"}, "inside the tests folder"),
        ({"shell": "x"}, "unknown fields"),
    ):
        with pytest.raises(ApiError, match=message):
            call(app, "POST", "/api/recording", {**base, **change})

    call(app, "POST", "/api/recording", {**base, "file": "no_pod.yaml"})
    failed = wait(lambda: (s := call(app, "GET", "/api/recording"))["status"] == "error" and s)
    assert failed["message"] == "set QM_FUSION_URL to the non-prod pod URL"


def test_http_guards(app: App) -> None:
    server = make_server(app, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port_of(server)}"

    def request(path: str, data: bytes | None = None, headers: dict[str, str] | None = None) -> tuple[int, bytes]:
        req = urllib.request.Request(base + path, data=data, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                return res.status, res.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    try:
        status, page = request("/")
        assert status == 200 and b"<title>Quartermaster</title>" in page
        assert request("/api/status", headers={"Host": "evil.example"})[0] == 403  # DNS rebinding
        body = json.dumps({"target": "hcm/pass.yaml"}).encode()
        as_json = {"Content-Type": "application/json"}
        assert request("/api/runs", body, {**as_json, "Origin": "http://evil.example"})[0] == 403  # other sites
        assert request("/api/runs", b"target=hcm", {"Content-Type": "application/x-www-form-urlencoded"})[0] == 415
        assert request("/api/runs", body, {**as_json, "Origin": base})[0] == 201
        assert request("/nothing")[0] == 404
    finally:
        server.shutdown()
        server.server_close()
