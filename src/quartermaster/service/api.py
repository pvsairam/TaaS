"""The local web service: a small JSON API plus the web pages, on this computer only.

Standard library only (`http.server`), so `qm serve` needs nothing beyond Quartermaster itself.
It listens on 127.0.0.1 and refuses requests addressed to any other host name, so other
computers and other web sites cannot start runs.

    GET  /api/status                 pod, credentials set or not, environment name and release, folders
    GET  /api/settings, POST /api/settings   {"environment_name", "release"}
    POST /api/check-pod              can this computer reach the pod now?
    POST /api/ai/check               does the AI chosen in Settings answer? (a one-word question)
    POST /api/ai/key                 {"key"} the AI key, kept in memory only until Quartermaster stops ("" forgets it)
    GET  /api/dashboard              pass rate, coverage, release readiness, activity
    GET  /api/attention              what needs a person, by kind
    GET  /api/tests                  test files in the tests folder, with their last result
    GET  /api/test?file=<path>       one test: steps in plain words, data, history, the file
    POST /api/test/accept-update     {"file", "step_index", "new"} accept a screen change
    GET  /api/runs                   run history, newest first
    POST /api/runs                   {"target": "hcm/view_worker.yaml", "options": {...}} queue a run
    GET  /api/runs/<id>              one run, its progress events and (when done) its results
    GET  /api/runs/<id>/events?after=N   progress events from line N on
    POST /api/runs/<id>/cancel
    GET  /api/recording              the recording in progress, or the last one
    POST /api/recording              {"id", "title", "module", "product", "persona", "file"} start recording
    POST /api/recording/<command>    pause, resume, check, undo, note {"text"}, mask, stop
    GET  /api/releases               release feature lists (the releases folder and imported ones)
    GET  /api/releases/plan?name=<file>&budget=<minutes>&opt_in=<feature id>   tests to run, and why
    POST /api/releases/import        {"name", "content" (base64), "release_id", "save"} a feature list
    GET  /api/manual                 imported manual test scripts: their files and scenarios
    GET  /api/manual/scenario?id=<id>   one manual scenario with its test cases and steps
    POST /api/manual/import          {"files": [{"name", "content" (base64), "module", "product"}], "save"}
    POST /api/manual/remove          {"key"} forget one imported workbook
    POST /api/manual/run             {"id", "by_hand", "prepare", "release", "tester"} run a scenario: it plays
                                     by itself once done by hand (or prepared by AI and approved); otherwise it is
                                     done by hand now, or with "prepare" an AI does it and it waits for review
    POST /api/manual/approve         {"id"} a person checked what the AI prepared: Run may now play it
    POST /api/open                   {"path": "<inside the evidence folder>"} open it in Explorer/Finder
    GET  /files/<path>               a file from the evidence folder (documents, pictures, videos)
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit

import yaml

from quartermaster.ai import providers as ai_providers
from quartermaster.evidence.document import plain_error
from quartermaster.service import insights
from quartermaster.service.heal import accept_update
from quartermaster.service.impact import Releases
from quartermaster.service.manual import ManualScripts
from quartermaster.service.recording import COMMANDS, RecordCommandBuilder, Recording, qm_record_command
from quartermaster.service.runner import DEFAULT_OPTIONS, CommandBuilder, RunQueue, qm_run_command
from quartermaster.service.settings import Settings, check_pod
from quartermaster.service.store import Store

WEB_DIR = Path(__file__).parent / "web"
_WEB_FILE = re.compile(r"^/([a-z0-9-]+\.(?:js|css))$")  # the page's own scripts and styles, nothing else
_TYPES = {
    ".txt": "text/plain; charset=utf-8",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".webm": "video/webm",
}


class ApiError(Exception):
    def __init__(self, status: HTTPStatus, message: str):
        super().__init__(message)
        self.status = status


@dataclass
class Reply:
    status: HTTPStatus
    body: bytes
    content_type: str = "application/json"
    download_name: str | None = None


def _json(data: Any, status: HTTPStatus = HTTPStatus.OK) -> Reply:
    return Reply(status, json.dumps(data).encode("utf-8"))


class App:
    def __init__(
        self,
        *,
        tests_root: Path,
        evidence_root: Path,
        data_dir: Path,
        run_command: CommandBuilder = qm_run_command,
        record_command: RecordCommandBuilder = qm_record_command,
        cwd: Path | None = None,
        releases_root: Path | None = None,
    ):
        self.tests_root = tests_root.resolve()
        self.evidence_root = evidence_root.resolve()
        self.queue = RunQueue(
            Store(data_dir / "qm.db"),
            tests_root=self.tests_root,
            evidence_root=self.evidence_root,
            work_dir=data_dir / "runs",
            command=run_command,
            cwd=cwd,
        )
        self.recording = Recording(self.tests_root, self.evidence_root, data_dir / "recording", record_command)
        self.backups = data_dir / "backups"
        self.settings = Settings(data_dir / "settings.json")
        self.pod_check: dict[str, Any] | None = None
        self.keys_entered: set[str] = set()  # AI keys pasted in Settings: in memory only, never on disk
        self.releases = Releases(releases_root, data_dir / "releases")
        self.manual = ManualScripts(data_dir / "manual")
        self.recording.on_manual_done = self._manual_done

    def start(self) -> None:
        self.evidence_root.mkdir(parents=True, exist_ok=True)
        self.queue.start()

    def stop(self) -> None:
        self.recording.shutdown()
        self.queue.stop()

    # ------------------------------------------------------------------ routing

    def handle(self, method: str, raw_path: str, body: bytes) -> Reply:
        url = urlsplit(raw_path)
        path, query = unquote(url.path), parse_qs(url.query)
        parts = [p for p in path.split("/") if p]
        if method == "GET" and path == "/":
            return self._page("index.html")
        web = _WEB_FILE.match(path)
        if method == "GET" and web and (WEB_DIR / web.group(1)).is_file():
            return self._page(web.group(1))
        if method == "GET" and parts[:1] == ["files"]:
            return self._file("/".join(parts[1:]))
        if parts[:1] != ["api"]:
            raise ApiError(HTTPStatus.NOT_FOUND, "not found")
        data = self._body(body) if method == "POST" else {}
        route = parts[1:]

        if method == "GET" and route == ["status"]:
            return _json(self.status())
        if method == "GET" and route == ["tests"]:
            return _json(self.tests())
        if route == ["settings"]:
            if method == "POST":
                try:
                    self.settings.update(data)
                except ValueError as e:
                    raise ApiError(HTTPStatus.BAD_REQUEST, str(e)) from e
            return _json(self.settings.get())
        if method == "POST" and route == ["ai", "key"]:
            return _json(self.set_ai_key(str(data.get("key") or "")))
        if method == "POST" and route == ["ai", "check"]:
            return _json(ai_providers.check(ai_providers.config_from(self.settings.get())))
        if method == "POST" and route == ["check-pod"]:
            self.pod_check = check_pod(os.environ.get("QM_FUSION_URL", ""))
            return _json(self.pod_check)
        if method == "GET" and route == ["dashboard"]:
            release = self.settings.get()["release"]
            return _json(insights.dashboard(self.tests(), self.queue.store.list(limit=500), release))
        if method == "GET" and route == ["attention"]:
            return _json(self.attention())
        if method == "GET" and route == ["test"]:
            return _json(self.test_detail(str((query.get("file") or [""])[0])))
        if method == "POST" and route == ["test", "accept-update"]:
            return _json(self.accept_update(data))
        if route == ["runs"]:
            if method == "GET":
                return _json([self._run_view(r, counts=True) for r in self.queue.store.list()])
            if method == "POST":
                options = dict(data.get("options") or {})
                if not str(options.get("release") or "").strip():
                    options["release"] = self.settings.get()["release"]  # the environment's release by default
                try:
                    queued = self.queue.submit(str(data.get("target") or ""), options)
                except ValueError as e:
                    raise ApiError(HTTPStatus.BAD_REQUEST, str(e)) from e
                return _json(self._run_view(queued), HTTPStatus.CREATED)
        if len(route) >= 2 and route[0] == "runs":
            run = self.queue.store.get(route[1])
            if run is None:
                raise ApiError(HTTPStatus.NOT_FOUND, "no such run")
            if method == "GET" and len(route) == 2:
                return _json(self.run_detail(run))
            if method == "GET" and route[2:] == ["events"]:
                after = int((query.get("after") or ["0"])[0] or 0)
                return _json([_with_plain_error(e) for e in self.queue.events(run["id"], after=max(after, 0))])
            if method == "POST" and route[2:] == ["cancel"]:
                return _json(self._run_view(self.queue.cancel(run["id"]) or run))
        if route[:1] == ["recording"]:
            if method == "GET" and len(route) == 1:
                return _json(self._recording_view())
            if method == "POST" and len(route) == 1:
                try:
                    return _json(self.recording.start(data), HTTPStatus.CREATED)
                except ValueError as e:
                    raise ApiError(HTTPStatus.BAD_REQUEST, str(e)) from e
            if method == "POST" and len(route) == 2 and route[1] in COMMANDS:
                try:
                    return _json(self.recording.send(route[1], str(data.get("text") or "")))
                except ValueError as e:
                    raise ApiError(HTTPStatus.CONFLICT, str(e)) from e
        if route[:1] == ["releases"]:
            return self._releases(method, route[1:], query, data)
        if route[:1] == ["manual"]:
            return self._manual(method, route[1:], query, data)
        if method == "POST" and route == ["open"]:
            return _json({"opened": str(self._open(str(data.get("path") or "")))})
        raise ApiError(HTTPStatus.NOT_FOUND, "not found")

    def _releases(self, method: str, route: list[str], query: dict[str, list[str]], data: dict[str, Any]) -> Reply:
        try:
            if method == "GET" and not route:
                return _json(self.releases.list())
            if method == "GET" and route == ["plan"]:
                budget = str((query.get("budget") or [""])[0]).strip()
                opt_ins = {o for v in query.get("opt_in") or [] for o in v.split(",") if o}
                name = str((query.get("name") or [""])[0])
                limit = float(budget) if budget else None
                return _json(self.releases.plan(name, self.tests_root, limit, opt_ins, self.manual))
            if method == "POST" and route == ["import"]:
                return _json(self.releases.import_file(data), HTTPStatus.CREATED if data.get("save") else HTTPStatus.OK)
        except LookupError as e:
            raise ApiError(HTTPStatus.NOT_FOUND, str(e).strip("'\"")) from e
        except ValueError as e:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(e)) from e
        raise ApiError(HTTPStatus.NOT_FOUND, "not found")

    def _manual(self, method: str, route: list[str], query: dict[str, list[str]], data: dict[str, Any]) -> Reply:
        try:
            if method == "GET" and not route:
                summary = self.manual.summary()
                self._with_results(summary["scenarios"])
                return _json(summary)
            if method == "GET" and route == ["scenario"]:
                scenario = self.manual.get(str((query.get("id") or [""])[0]))
                self._with_results([scenario], history=True)
                return _json(scenario)
            if method == "POST" and route == ["run"]:
                return _json(self.run_manual(data), HTTPStatus.CREATED)
            if method == "POST" and route == ["approve"]:
                return _json(self.manual.approve(self.manual.get(str(data.get("id") or ""))["id"]))
            if method == "POST" and route == ["import"]:
                return _json(self.manual.import_files(data))
            if method == "POST" and route == ["remove"]:
                return _json(self.manual.remove(str(data.get("key") or "")))
        except LookupError as e:
            raise ApiError(HTTPStatus.NOT_FOUND, str(e)) from e
        except ValueError as e:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(e)) from e
        raise ApiError(HTTPStatus.NOT_FOUND, "not found")

    def set_ai_key(self, key: str) -> dict[str, Any]:
        """Keep the AI key pasted in Settings for as long as Quartermaster runs. It is put in this
        process's environment, where the AI runs started from here find it, and is never written to
        a file or sent back to the page."""
        config = ai_providers.config_from(self.settings.get())
        if not config.provider:
            raise ApiError(HTTPStatus.BAD_REQUEST, "choose and save an AI provider first")
        if not config.key_env:
            raise ApiError(HTTPStatus.BAD_REQUEST, "this provider needs no key")
        key = key.strip()
        if not key:
            if config.key_env in self.keys_entered:
                os.environ.pop(config.key_env, None)
                self.keys_entered.discard(config.key_env)
            return self._ai_view(self.settings.get())
        if len(key) < 8 or len(key) > 500 or any(c.isspace() for c in key):
            raise ApiError(
                HTTPStatus.BAD_REQUEST, "that does not look like an API key (no spaces, at least 8 characters)"
            )
        os.environ[config.key_env] = key
        self.keys_entered.add(config.key_env)
        return self._ai_view(self.settings.get())

    def _ai_view(self, settings: dict[str, Any]) -> dict[str, Any]:
        """The AI choice for the Settings page: never the key itself, only whether it is set and where from."""
        config = ai_providers.config_from(settings)
        has_key = bool(config.key())
        return {
            "key_source": ("entered" if config.key_env in self.keys_entered else "computer") if has_key else "",
            "provider": config.provider,
            "model": config.model,
            "base_url": config.base_url,
            "key_env": config.key_env,
            "workspace": config.workspace,
            "key_set": bool(config.key()),
            "label": config.label if config.provider else "",
            "problem": config.problem() if config.provider else "No AI provider is chosen.",
            "presets": [
                {"id": k, "label": v[0], "format": v[1], "base_url": v[2], "key_env": v[3], "model": v[4]}
                for k, v in ai_providers.PRESETS.items()
            ],
        }

    # ------------------------------------------------------------------ manual scenarios run

    def run_manual(self, data: dict[str, Any]) -> dict[str, Any]:
        """Once a scenario has been done by hand, Run plays it by itself; before that (or when asked
        with by_hand) the tester does it by hand while Quartermaster takes pictures and records."""
        scenario = self.manual.get(str(data.get("id") or ""))
        rel = self.manual.test_file(scenario["id"])
        release = str(data.get("release") or self.settings.get()["release"] or "").strip()
        tester = str(data.get("tester") or "").strip()
        if data.get("prepare"):
            config = ai_providers.config_from(self.settings.get())
            problem = config.problem() if config.provider else "Choose an AI provider in Settings first."
            if problem:
                raise ValueError(problem)
            ai = {
                "provider": config.provider,
                "model": config.model,
                "base_url": config.base_url,
                "key_env": config.key_env,
                "workspace": config.workspace,
            }
            state = self.recording.start_guided(
                scenario, test_id=self.manual.test_id(scenario["id"]), rel_file=rel, release=release, ai=ai
            )
            return {"mode": "prepare", "recording": state}
        if (self.tests_root / rel).is_file() and not data.get("by_hand"):
            review = self.manual.reviews().get(scenario["id"])
            if review and not review.get("approved_at"):
                raise ValueError("An AI prepared this scenario. Check its pictures and approve it before it runs.")
            # the evidence choices remembered from New run (screenshots, video, show the browser)
            chosen = data.get("options") if isinstance(data.get("options"), dict) else {}
            options = {k: chosen[k] for k in ("screenshots", "video", "headed") if k in chosen}
            options.update(label=f"Automatic: {scenario['title']}"[:80], release=release, tester=tester)
            return {"mode": "automatic", "run": self._run_view(self.queue.submit(rel, options))}
        state = self.recording.start_guided(
            scenario, test_id=self.manual.test_id(scenario["id"]), rel_file=rel, release=release, tester=tester
        )
        return {"mode": "by_hand", "recording": state}

    def _manual_done(self, state: dict[str, Any]) -> dict[str, Any] | None:
        """A scenario done by hand has been saved: put it in the run history like any other run."""
        if not state.get("suite_dir"):
            return None
        options = {
            **DEFAULT_OPTIONS,
            "release": state.get("release", ""),
            "tester": state.get("tester", ""),
            "headed": True,
            "label": f"By hand: {state.get('title', '')}"[:80],
        }
        by_ai = state.get("mode") == "ai"
        if by_ai:
            options["label"] = f"Prepared by AI: {state.get('title', '')}"[:80]
            options["tester"] = "AI"
        run = self.queue.store.add_finished(
            str(state.get("file", "")),
            options,
            status="passed" if state.get("result") == "passed" else "failed",
            started_at=state.get("started_at"),
            finished_at=state.get("finished_at"),
            suite_dir=state.get("suite_dir"),
            summary=state.get("summary") or None,
        )
        scenario_id = str(state.get("scenario_id") or "")
        if by_ai and state.get("automated"):
            self.manual.mark_prepared(scenario_id, run["id"], ai_providers.config_from(self.settings.get()).label)
        elif not by_ai and state.get("automated"):
            self.manual.checked_by_hand(scenario_id)
        return run

    def _recording_view(self) -> dict[str, Any]:
        state = self.recording.state()
        feed = state.get("feed") or {}
        folder = self._relative(feed.get("guide_folder"))
        for step in feed.get("guide") or []:
            picture = step.get("picture")
            step["picture_url"] = self._url_rel(f"{folder}/{picture}") if folder and picture else None
        if state.get("run_id"):
            run = self.queue.store.get(str(state["run_id"]))
            results = self._suite_results(run) if run else []
            state["document_url"] = results[0]["document_url"] if results else None
            folder = folder or (results[0]["folder"] if results else None)  # the feed is gone once it is saved
        diary = f"{folder}/ai-diary.txt" if folder else ""
        state["diary_url"] = self._url_rel(diary) if diary and (self.evidence_root / diary).is_file() else None
        return state

    def _with_results(self, scenarios: list[dict[str, Any]], history: bool = False) -> None:
        """Each scenario's own results in Quartermaster (not what the workbook says): the latest, and
        whether it now plays by itself."""
        runs = self.queue.store.list(limit=500)
        results = insights.test_results(runs)
        by_test: dict[str, list[dict[str, Any]]] = {}
        for r in results:
            by_test.setdefault(r["test_id"], []).append(r)
        reviews = self.manual.reviews()
        for s in scenarios:
            review = reviews.get(str(s.get("id", "")))
            s["review"] = None if not review else ("approved" if review.get("approved_at") else "needs_review")
            s["prepared"] = review
            mine = by_test.get(self.manual.test_id(str(s.get("id", ""))), [])
            s["automated"] = (self.tests_root / self.manual.test_file(str(s.get("id", "")))).is_file()
            s["test_file"] = self.manual.test_file(str(s.get("id", "")))
            s["qm_result"] = _result_view(mine[0]) if mine else None
            if history:
                s["qm_history"] = [_result_view(r) for r in mine[:20]]

    # ------------------------------------------------------------------ views

    def status(self) -> dict[str, Any]:
        url = os.environ.get("QM_FUSION_URL", "")
        settings = self.settings.get()
        runs = self.queue.store.list(limit=1)
        return {
            **settings,
            "pod_url": url,
            "pod_host": urlsplit(url).hostname or "",
            "pod_check": self.pod_check,
            "last_run": self._run_view(runs[0]) if runs else None,
            "user": os.environ.get("QM_FUSION_USER", ""),
            "password_set": bool(os.environ.get("QM_FUSION_PASSWORD")),
            "tests_folder": str(self.tests_root),
            "releases_folder": str(self.releases.folder or ""),
            "evidence_folder": str(self.evidence_root),
            "default_options": DEFAULT_OPTIONS,
            "ai": self._ai_view(settings),
            "ready": bool(url and os.environ.get("QM_FUSION_USER") and os.environ.get("QM_FUSION_PASSWORD")),
        }

    def tests(self) -> list[dict[str, Any]]:
        runs = self.queue.store.list(limit=500)  # newest first
        last: dict[str, dict[str, Any]] = {}
        for run in runs:
            last.setdefault(run["target"], run)
        latest: dict[str, dict[str, Any]] = {}  # each test's own latest result, whatever run it was part of
        validated: dict[str, str] = {}  # the release each test last passed on
        for r in insights.test_results(runs):
            latest.setdefault(
                r["test_id"],
                {
                    "status": r["status"],
                    "at": r["at"],
                    "run_id": r["service_run_id"],
                    "release": r["release"],
                    "duration": r.get("duration"),
                    "environment": urlsplit(r.get("environment_url") or "").hostname,
                },
            )
            if r["status"] in insights.PASSING and r["release"]:
                validated.setdefault(r["test_id"], r["release"])
        out = []
        for f in sorted(self.tests_root.rglob("*.y*ml")):
            rel = f.relative_to(self.tests_root).as_posix()
            item: dict[str, Any] = {
                "file": rel,
                "folder": rel.rpartition("/")[0],
                "updated": datetime.fromtimestamp(f.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
            }
            try:
                spec = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
                if not isinstance(spec, dict):
                    raise ValueError("not a test spec")
                item.update(
                    id=str(spec.get("id", "")),
                    title=str(spec.get("title", "")),
                    module=str(spec.get("module", "")),
                    product=str(spec.get("product", "")),
                    process=str(spec.get("process", "")),
                    persona=str(spec.get("persona", "")),
                    priority=str(spec.get("priority", "")),
                    tags=[str(t) for t in spec.get("tags") or []],
                    owner=str(spec.get("owner", "")),
                    steps=len(spec.get("steps") or []),
                )
            except (yaml.YAMLError, ValueError, OSError) as e:
                item["problem"] = f"Could not read this file: {e}"
            previous = last.get(rel)
            item["last_run"] = self._run_view(previous) if previous else None
            item["last_result"] = latest.get(item.get("id", ""))
            item["release_validated"] = validated.get(item.get("id", ""))
            out.append(item)
        return out

    def test_detail(self, rel: str) -> dict[str, Any]:
        path = self._test_file(rel)
        text = path.read_text(encoding="utf-8")
        item = next((t for t in self.tests() if t["file"] == path.relative_to(self.tests_root).as_posix()), {})
        try:
            loaded = yaml.safe_load(text)
        except yaml.YAMLError:
            loaded = None
        spec: dict[str, Any] = loaded if isinstance(loaded, dict) else {}
        data: dict[str, Any] = spec["data"] if isinstance(spec.get("data"), dict) else {}
        steps = []
        for i, step in enumerate(spec.get("steps") or []):
            if not isinstance(step, dict):
                continue
            target: dict[str, Any] = step["target"] if isinstance(step.get("target"), dict) else {}
            strategies = [s for s in target.get("strategies") or [] if isinstance(s, dict)]
            found_by = [insights.describe([str(k), _fill(str(v), data)]) for s in strategies for k, v in s.items()]
            steps.append(
                {
                    "number": i + 1,
                    "action": step.get("action", ""),
                    "intent": step.get("intent", ""),
                    "value": "" if step.get("value") is None else _fill(str(step.get("value")), data),
                    "found_by": found_by,
                }
            )
        history = insights.test_history(item.get("id", ""), self.queue.store.list(limit=500))
        for h in history:
            h["document_url"] = self._url_rel(h.pop("document"))
        tested = [h for h in history if h["status"] in ("passed", "healed", "failed")]
        passed = sum(h["status"] != "failed" for h in tested)
        return {
            **item,
            "data": data,
            "steps_detail": steps,
            "yaml": text,
            "history": history,
            "pass_rate": round(100 * passed / len(tested)) if tested else None,
        }

    def attention(self) -> dict[str, Any]:
        result = insights.attention(
            self.tests(), self.queue.store.list(limit=500), self.tests_root, self.settings.get()["release"]
        )
        for item in result["items"]:
            item["picture_url"] = self._url_rel(item.pop("picture", None))
            item["document_url"] = self._url_rel(item.pop("document", None))
        return result

    def accept_update(self, data: dict[str, Any]) -> dict[str, Any]:
        path = self._test_file(str(data.get("file") or ""))
        try:
            backup = accept_update(
                path, int(data.get("step_index", -1)), [str(x) for x in data.get("new") or []], self.backups
            )
        except ValueError as e:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(e)) from e
        return {"updated": path.relative_to(self.tests_root).as_posix(), "backup": str(backup)}

    def _test_file(self, rel: str) -> Path:
        path = (self.tests_root / rel).resolve()
        if self.tests_root not in path.parents or path.suffix.lower() not in (".yaml", ".yml"):
            raise ApiError(HTTPStatus.FORBIDDEN, "only test files in the tests folder can be opened")
        if not path.is_file():
            raise ApiError(HTTPStatus.NOT_FOUND, "no such test file")
        return path

    def run_detail(self, run: dict[str, Any]) -> dict[str, Any]:
        view = self._run_view(run)
        view["events"] = [_with_plain_error(e) for e in self.queue.events(run["id"])]
        view["results"] = self._suite_results(run)
        log = Path(run["log_path"]) if run.get("log_path") else None
        view["output"] = _tail(log) if log and log.is_file() else ""
        return view

    def _run_view(self, run: dict[str, Any], counts: bool = False) -> dict[str, Any]:
        view = {k: v for k, v in run.items() if k not in ("events_path", "log_path")}
        view["summary_url"] = self._url(run.get("summary"))
        view["suite_folder"] = self._relative(run.get("suite_dir"))
        suite = insights.suite_of(run) or {}
        # what the evidence says, else what was asked for
        view["release"] = str(suite.get("release") or run["options"].get("release") or "")
        view["executed_by"] = str(suite.get("executed_by") or run["options"].get("tester") or "")
        view["environment"] = urlsplit(str(suite.get("environment_url") or "")).hostname or None
        if counts:
            view["counts"] = insights.run_counts(run)
        return view

    def _suite_results(self, run: dict[str, Any]) -> list[dict[str, Any]]:
        """Each test's result with links to its evidence, from the suite record once the run has ended."""
        if not run.get("suite_dir"):
            return []
        suite_json = Path(run["suite_dir"]) / "suite.json"
        if not suite_json.is_file():
            return []
        suite = json.loads(suite_json.read_text(encoding="utf-8"))
        results = []
        for entry in suite.get("runs", []):
            run_dir = self.evidence_root / entry["run_dir"]
            record_file = run_dir / "run.json"
            record = insights.read_json(record_file) or {}
            failed = entry.get("failed_step") or None
            results.append(
                {
                    **{k: entry.get(k) for k in ("test_id", "test_title", "status", "steps_total", "steps_passed")},
                    "duration": entry.get("duration"),
                    "folder": entry["run_dir"],
                    "document_url": self._url_rel(entry.get("document")),
                    "videos": [self._url_rel(f"{entry['run_dir']}/{v}") for v in record.get("videos", [])],
                    "failed_step": failed
                    and {
                        "number": failed.get("number"),
                        "intent": failed.get("intent"),
                        "error": plain_error(failed.get("error")),
                        "detail": failed.get("error"),
                        "picture_url": self._url_rel(failed.get("screenshot")),
                    },
                    "needs_update": bool(entry.get("healing")),
                    "started_at": record.get("started_at"),
                    "finished_at": record.get("finished_at"),
                    "record_url": self._url_rel(f"{entry['run_dir']}/run.json") if record else None,
                    "steps": [
                        {
                            "number": st.get("index", 0) + 1,
                            "intent": st.get("intent", ""),
                            "action": st.get("action", ""),
                            "by": record.get("mode", "automatic"),  # "manual" or "ai" for manual scenarios
                            "value": st.get("value"),
                            "expected": st.get("expected", ""),
                            "status": st.get("status", ""),
                            "error": plain_error(st.get("error")),
                            "detail": st.get("error"),
                            "compare": insights.expected_observed(st.get("error")),
                            "locator": st.get("locator"),
                            "started_at": st.get("started_at"),
                            "seconds": round((st.get("duration_ms") or 0) / 1000, 1),
                            "screenshot_note": st.get("screenshot_note"),
                            "pictures": [self._url_rel(f"{entry['run_dir']}/{p}") for p in st.get("evidence") or []],
                        }
                        for st in record.get("steps", [])
                    ],
                }
            )
        return results

    # ------------------------------------------------------------------ files

    def _inside_evidence(self, rel: str) -> Path:
        path = (self.evidence_root / rel).resolve()
        if path != self.evidence_root and self.evidence_root not in path.parents:
            raise ApiError(HTTPStatus.FORBIDDEN, "only files in the evidence folder can be opened")
        if not path.exists():
            raise ApiError(HTTPStatus.NOT_FOUND, "that file is no longer there")
        return path

    def _file(self, rel: str) -> Reply:
        path = self._inside_evidence(rel)
        if not path.is_file():
            raise ApiError(HTTPStatus.NOT_FOUND, "not a file")
        kind = _TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        download = path.name if path.suffix.lower() == ".docx" else None
        return Reply(HTTPStatus.OK, path.read_bytes(), kind, download)

    def _open(self, rel: str) -> Path:
        path = self._inside_evidence(rel)
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined,unused-ignore]  # Windows only
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])
        return path

    def _page(self, name: str) -> Reply:
        kind = {"html": "text/html", "js": "text/javascript", "css": "text/css"}[name.rsplit(".", 1)[1]]
        return Reply(HTTPStatus.OK, (WEB_DIR / name).read_bytes(), f"{kind}; charset=utf-8")

    def _relative(self, path: str | None) -> str | None:
        if not path:
            return None
        try:
            return Path(path).resolve().relative_to(self.evidence_root).as_posix()
        except ValueError:
            return None

    def _url(self, path: str | None) -> str | None:
        return self._url_rel(self._relative(path))

    @staticmethod
    def _url_rel(rel: str | None) -> str | None:
        return f"/files/{quote(rel)}" if rel else None

    @staticmethod
    def _body(body: bytes) -> dict[str, Any]:
        try:
            data = json.loads(body or b"{}")
        except json.JSONDecodeError as e:
            raise ApiError(HTTPStatus.BAD_REQUEST, "the request is not valid JSON") from e
        if not isinstance(data, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "the request must be a JSON object")
        return data


def _result_view(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": r.get("status"),
        "at": r.get("at"),
        "run_id": r.get("service_run_id"),
        "release": r.get("release"),
        "by_hand": r.get("mode") == "manual",
        "how": {"manual": "by_hand", "ai": "prepared"}.get(str(r.get("mode")), "automatic"),
    }


def _fill(text: str, data: dict[str, Any]) -> str:
    """Show ${name} placeholders with the test data they stand for (unknown names stay as written)."""
    return re.sub(r"\$\{(\w+)\}", lambda m: str(data[m.group(1)]) if m.group(1) in data else m.group(0), text)


def _with_plain_error(event: dict[str, Any]) -> dict[str, Any]:
    """Failed steps also carry the problem in everyday words, as the evidence document puts it."""
    return {**event, "plain_error": plain_error(event["error"])} if event.get("error") else event


def _tail(log: Path, n: int = 40) -> str:
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-n:])


# ---------------------------------------------------------------------- HTTP


def port_of(server: Any) -> int:
    return int(server.server_address[1])


def make_server(app: App, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        server_version = "Quartermaster"

        def do_GET(self) -> None:
            self._serve("GET")

        def do_POST(self) -> None:
            self._serve("POST")

        def _serve(self, method: str) -> None:
            try:
                self._check_origin(method)
                length = int(self.headers.get("Content-Length") or 0)
                reply = app.handle(method, self.path, self.rfile.read(length) if length else b"")
            except ApiError as e:
                reply = _json({"error": str(e)}, e.status)
            except Exception as e:  # keep serving; show the problem in the page
                reply = _json({"error": f"{type(e).__name__}: {e}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            self.send_response(reply.status)
            self.send_header("Content-Type", reply.content_type)
            self.send_header("Content-Length", str(len(reply.body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if reply.download_name:
                self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(reply.download_name)}")
            self.end_headers()
            self.wfile.write(reply.body)

        def _check_origin(self, method: str) -> None:
            """Only pages served by this service, on this computer, may use it."""
            port_now = port_of(self.server)
            allowed = {f"127.0.0.1:{port_now}", f"localhost:{port_now}"}
            if self.headers.get("Host") not in allowed:
                raise ApiError(HTTPStatus.FORBIDDEN, f"open Quartermaster at http://127.0.0.1:{port_now}")
            if method == "POST":
                origin = self.headers.get("Origin")
                if origin is not None and urlsplit(origin).netloc not in allowed:
                    raise ApiError(HTTPStatus.FORBIDDEN, "requests from other web sites are not allowed")
                if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
                    raise ApiError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "send JSON")

        def log_message(self, format: str, *args: Any) -> None:
            pass  # quiet: the page shows what happens

    return ThreadingHTTPServer((host, port), Handler)
