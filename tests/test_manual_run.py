"""Running a manual scenario from the web UI: by hand the first time, by itself after that.
A stand-in plays `qm record --guide` (the real one opens a browser); see test_guided.py for that."""

from __future__ import annotations

import base64
import json
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from test_manual_scripts import ACTIONS, EXAMPLES
from test_release_import import make_xlsx
from test_service_api import call, wait
from test_service_queue import fake_command

from quartermaster.service.api import ApiError, App
from quartermaster.service.recording import qm_record_command

# Stand-in for `qm record --guide`: takes "result <n> pass|fail" lines like the real one, keeps
# the marks in its feed, and on "stop" writes a run like the real one (suite.json, a test file).
FAKE_GUIDED = r"""
import json, os, sys
out, rest = sys.argv[1], sys.argv[2:]
opt = dict(zip(rest[::2], rest[1::2]))
tid, evidence, feed = opt['--id'], opt['--evidence'], opt['--events']
json.load(open(opt['--guide']))  # the scenario must arrive
run_dir = os.path.join(evidence, tid, 'r1')
os.makedirs(os.path.join(run_dir, 'screenshots'), exist_ok=True)
marks = {}
while True:
    line = sys.stdin.readline().strip()
    if line in ('', 'stop'):
        break
    word, n, status = (line.split() + ['', ''])[:3]
    if word == 'result':
        picture = 'screenshots/step-%02d.png' % int(n)
        open(os.path.join(run_dir, picture), 'wb').write(b'png')
        marks[int(n)] = 'passed' if status == 'pass' else 'failed'
        guide = [{'number': k, 'status': v, 'picture': 'screenshots/step-%02d.png' % k} for k, v in marks.items()]
        json.dump({'steps': [], 'guide': guide, 'guide_folder': run_dir, 'message': ''}, open(feed, 'w'))
if not marks:
    print('error: no step was marked Pass or Fail, so nothing was saved'); sys.exit(2)
status = 'failed' if 'failed' in marks.values() else 'passed'
suite_dir = os.path.join(evidence, '_suites', 'S-' + tid)
os.makedirs(suite_dir, exist_ok=True)
entry = {'test_id': tid, 'status': status, 'run_dir': tid + '/r1', 'document': None, 'mode': 'manual',
         'steps_total': len(marks), 'steps_passed': sum(v == 'passed' for v in marks.values())}
json.dump({'release': opt.get('--release'), 'runs': [entry]}, open(os.path.join(suite_dir, 'suite.json'), 'w'))
os.makedirs(os.path.dirname(out), exist_ok=True)
open(out, 'w').write('id: ' + tid + '\n')
print('Saved 1 step(s) to ' + out + '. Replay with: qm run ' + out)
print('Manual run: ' + suite_dir)
print('Summary document: ' + os.path.join(suite_dir, 's.docx'))
print('Result: ' + status)
"""


def fake_guided(out: Path, fields: dict[str, str], evidence_root: Path, feed: Path) -> list[str]:
    real = qm_record_command(out, fields, evidence_root, feed)  # the real flags, to check they are passed
    assert real[1:4] == ["-m", "quartermaster.cli", "record"]
    return [sys.executable, "-c", FAKE_GUIDED, *real[4:]]


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[App]:
    monkeypatch.setenv("QM_FUSION_URL", "https://abcd-dev2.fa.us6.oraclecloud.com")
    tests = tmp_path / "tests"
    shutil.copytree(EXAMPLES / "tests", tests)
    a = App(
        tests_root=tests,
        evidence_root=tmp_path / "evidence",
        data_dir=tmp_path / ".qm",
        run_command=fake_command,
        record_command=fake_guided,
    )
    a.start()
    content = base64.b64encode(make_xlsx({"Sheet1": ACTIONS})).decode()
    call(
        a, "POST", "/api/manual/import", {"files": [{"name": "ESS Test Script.xlsx", "content": content}], "save": True}
    )
    yield a
    a.stop()


def scenario(app: App, ref: str) -> dict[str, Any]:
    return next(s for s in call(app, "GET", "/api/manual")["scenarios"] if s["ref"] == ref)


def test_by_hand_first_then_by_itself(app: App) -> None:
    pay = scenario(app, "ESS-001")
    assert (pay["automated"], pay["qm_result"]) == (False, None)  # "Pass in workbook" is not a Quartermaster result
    assert pay["test_file"] == "manual/ess-test-script/ess-001.yaml"

    started = call(app, "POST", "/api/manual/run", {"id": pay["id"], "release": "26C", "tester": "Sai"})
    assert started["mode"] == "by_hand" and started["recording"]["mode"] == "manual"
    assert started["recording"]["test_id"] == "manual.ess-test-script.ess-001"
    with pytest.raises(ApiError, match="already in progress"):
        app.handle("POST", "/api/manual/run", json.dumps({"id": pay["id"]}).encode())

    call(app, "POST", "/api/recording/result", {"text": "1 pass"})
    call(app, "POST", "/api/recording/result", {"text": "2 pass"})
    shown = wait(lambda: (call(app, "GET", "/api/recording").get("feed") or {}).get("guide"))
    assert shown[0]["picture_url"] == "/files/manual.ess-test-script.ess-001/r1/screenshots/step-01.png"
    call(app, "POST", "/api/recording/stop")
    done = wait(lambda: (lambda s: s if s.get("run_id") else None)(call(app, "GET", "/api/recording")))
    assert (done["status"], done["result"], done["automated"]) == ("saved", "passed", True)

    run = call(app, "GET", "/api/runs")[0]
    assert run["id"] == done["run_id"] and run["status"] == "passed"
    assert run["options"]["label"] == "By hand: My Compensation" and run["release"] == "26C"
    assert run["target"] == "manual/ess-test-script/ess-001.yaml"

    pay = scenario(app, "ESS-001")
    assert pay["automated"] is True
    assert pay["qm_result"] == {**pay["qm_result"], "status": "passed", "by_hand": True, "release": "26C"}
    detail = call(app, "GET", "/api/manual/scenario?id=" + pay["id"])
    assert len(detail["qm_history"]) == 1 and detail["cases"]

    # Next time: Run plays the recorded test by itself, through the run queue.
    again = call(app, "POST", "/api/manual/run", {"id": pay["id"]})
    assert again["mode"] == "automatic" and again["run"]["target"] == pay["test_file"]
    assert again["run"]["options"]["label"] == "Automatic: My Compensation"
    assert wait(lambda: call(app, "GET", f"/api/runs/{again['run']['id']}")["status"] == "passed")

    # It can still be done by hand on request; finishing without any mark saves nothing.
    assert call(app, "POST", "/api/manual/run", {"id": pay["id"], "by_hand": True})["mode"] == "by_hand"
    call(app, "POST", "/api/recording/stop")
    failed = wait(lambda: (lambda s: s if s["status"] == "error" else None)(call(app, "GET", "/api/recording")))
    assert "nothing was saved" in failed["message"]
    assert len(call(app, "GET", "/api/runs")) == 2


def test_a_failed_step_fails_the_run(app: App) -> None:
    contact = scenario(app, "ESS-003")
    call(app, "POST", "/api/manual/run", {"id": contact["id"]})
    call(app, "POST", "/api/recording/result", {"text": "1 pass"})
    call(app, "POST", "/api/recording/result", {"text": "2 fail the page did not open"})
    wait(lambda: len((call(app, "GET", "/api/recording").get("feed") or {}).get("guide") or []) == 2)
    call(app, "POST", "/api/recording/stop")
    done = wait(lambda: (lambda s: s if s.get("run_id") else None)(call(app, "GET", "/api/recording")))
    assert done["result"] == "failed"
    assert call(app, "GET", "/api/runs")[0]["status"] == "failed"
    assert scenario(app, "ESS-003")["qm_result"]["status"] == "failed"
    with pytest.raises(ApiError, match="no manual scenario"):
        app.handle("POST", "/api/manual/run", json.dumps({"id": "nope"}).encode())
