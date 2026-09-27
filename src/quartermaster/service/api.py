"""The local web service: a small JSON API plus the web pages, on this computer only.

Standard library only (`http.server`), so `qm serve` needs nothing beyond Quartermaster itself.
It listens on 127.0.0.1 and refuses requests addressed to any other host name, so other
computers and other web sites cannot start runs.

    GET  /api/status                 pod, credentials set or not, folders
    GET  /api/tests                  test files in the tests folder, with their last result
    GET  /api/runs                   run history, newest first
    POST /api/runs                   {"target": "hcm/view_worker.yaml", "options": {...}} queue a run
    GET  /api/runs/<id>              one run, its progress events and (when done) its results
    GET  /api/runs/<id>/events?after=N   progress events from line N on
    POST /api/runs/<id>/cancel
    GET  /api/recording              the recording in progress, or the last one
    POST /api/recording              {"id", "title", "module", "product", "persona", "file"} start recording
    POST /api/recording/stop
    POST /api/open                   {"path": "<inside the evidence folder>"} open it in Explorer/Finder
    GET  /files/<path>               a file from the evidence folder (documents, pictures, videos)
"""

from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import sys
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit

import yaml

from quartermaster.evidence.document import plain_error
from quartermaster.service.recording import RecordCommandBuilder, Recording, qm_record_command
from quartermaster.service.runner import DEFAULT_OPTIONS, CommandBuilder, RunQueue, qm_run_command
from quartermaster.service.store import Store

WEB_DIR = Path(__file__).parent / "web"
_PAGES = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
_TYPES = {".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".webm": "video/webm"}


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
        if method == "GET" and path in _PAGES:
            return self._page(_PAGES[path])
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
        if route == ["runs"]:
            if method == "GET":
                return _json([self._run_view(r) for r in self.queue.store.list()])
            if method == "POST":
                try:
                    queued = self.queue.submit(str(data.get("target") or ""), data.get("options") or {})
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
                return _json(self.recording.state())
            if method == "POST" and len(route) == 1:
                try:
                    return _json(self.recording.start(data), HTTPStatus.CREATED)
                except ValueError as e:
                    raise ApiError(HTTPStatus.BAD_REQUEST, str(e)) from e
            if method == "POST" and route[1:] == ["stop"]:
                return _json(self.recording.stop())
        if method == "POST" and route == ["open"]:
            return _json({"opened": str(self._open(str(data.get("path") or "")))})
        raise ApiError(HTTPStatus.NOT_FOUND, "not found")

    # ------------------------------------------------------------------ views

    def status(self) -> dict[str, Any]:
        url = os.environ.get("QM_FUSION_URL", "")
        return {
            "pod_url": url,
            "user": os.environ.get("QM_FUSION_USER", ""),
            "password_set": bool(os.environ.get("QM_FUSION_PASSWORD")),
            "tests_folder": str(self.tests_root),
            "evidence_folder": str(self.evidence_root),
            "default_options": DEFAULT_OPTIONS,
            "ready": bool(url and os.environ.get("QM_FUSION_USER") and os.environ.get("QM_FUSION_PASSWORD")),
        }

    def tests(self) -> list[dict[str, Any]]:
        last: dict[str, dict[str, Any]] = {}
        for run in self.queue.store.list(limit=500):  # newest first
            last.setdefault(run["target"], run)
        out = []
        for f in sorted(self.tests_root.rglob("*.y*ml")):
            rel = f.relative_to(self.tests_root).as_posix()
            item: dict[str, Any] = {"file": rel, "folder": rel.rpartition("/")[0]}
            try:
                spec = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
                if not isinstance(spec, dict):
                    raise ValueError("not a test spec")
                item.update(
                    id=str(spec.get("id", "")),
                    title=str(spec.get("title", "")),
                    module=str(spec.get("module", "")),
                    product=str(spec.get("product", "")),
                    steps=len(spec.get("steps") or []),
                )
            except (yaml.YAMLError, ValueError, OSError) as e:
                item["problem"] = f"Could not read this file: {e}"
            previous = last.get(rel)
            item["last_run"] = self._run_view(previous) if previous else None
            out.append(item)
        return out

    def run_detail(self, run: dict[str, Any]) -> dict[str, Any]:
        view = self._run_view(run)
        view["events"] = [_with_plain_error(e) for e in self.queue.events(run["id"])]
        view["results"] = self._suite_results(run)
        log = Path(run["log_path"]) if run.get("log_path") else None
        view["output"] = _tail(log) if log and log.is_file() else ""
        return view

    def _run_view(self, run: dict[str, Any]) -> dict[str, Any]:
        view = {k: v for k, v in run.items() if k not in ("events_path", "log_path")}
        view["summary_url"] = self._url(run.get("summary"))
        view["suite_folder"] = self._relative(run.get("suite_dir"))
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
            record = json.loads(record_file.read_text(encoding="utf-8")) if record_file.is_file() else {}
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
