"""One `qm record` at a time, started and stopped from the web UI.

`qm record` opens its own browser window and ends when Stop recording is pressed there or when
Enter reaches its standard input, so the web UI's Stop button just sends a newline.
"""

from __future__ import annotations

import re
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from quartermaster.service.store import now

RecordCommandBuilder = Callable[[Path, dict[str, str], Path], list[str]]

FIELDS = ("id", "title", "module", "product", "persona")
_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def qm_record_command(out: Path, fields: dict[str, str], evidence_root: Path) -> list[str]:
    cmd = [sys.executable, "-m", "quartermaster.cli", "record", str(out), "--evidence", str(evidence_root)]
    for key in FIELDS:
        if fields.get(key):
            cmd += [f"--{key}", fields[key]]
    return cmd


def check_request(request: dict[str, Any], tests_root: Path) -> tuple[Path, dict[str, str]]:
    """The file to write (inside the tests folder, never over an existing test) and the test's details."""
    unknown = set(request) - {*FIELDS, "file"}
    if unknown:
        raise ValueError(f"unknown fields: {', '.join(sorted(unknown))}")
    fields = {k: str(request.get(k) or "").strip()[:200] for k in FIELDS}
    for key in ("id", "title", "module", "product"):
        if not fields[key]:
            raise ValueError(f"{key} is required")
    if not _ID.match(fields["id"]):
        raise ValueError("id may use lower-case letters, digits, dots, dashes and underscores, e.g. hcm.view-worker")
    name = str(request.get("file") or "").strip() or f"recorded/{fields['id'].replace('.', '_')}.yaml"
    if not name.endswith((".yaml", ".yml")):
        name += ".yaml"
    out = (tests_root / name).resolve()
    if tests_root not in out.parents:
        raise ValueError("the file must be inside the tests folder")
    if out.exists():
        raise ValueError(f"{name} already exists; choose another file name")
    return out, fields


class Recording:
    def __init__(self, tests_root: Path, evidence_root: Path, work_dir: Path, command: RecordCommandBuilder):
        self.tests_root = tests_root.resolve()
        self.evidence_root = evidence_root
        self.work_dir = work_dir
        self.command = command
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[bytes] | None = None
        self._state: dict[str, Any] = {"status": "idle"}

    def start(self, request: dict[str, Any]) -> dict[str, Any]:
        out, fields = check_request(request, self.tests_root)
        with self._lock:
            if self._proc is not None:
                raise ValueError("a recording is already in progress; stop it first")
            self.work_dir.mkdir(parents=True, exist_ok=True)
            log = self.work_dir / "recording.log"
            with log.open("wb") as f:
                proc = subprocess.Popen(
                    self.command(out, fields, self.evidence_root),
                    stdin=subprocess.PIPE,  # kept open: a closed input would count as pressing Enter
                    stdout=f,
                    stderr=subprocess.STDOUT,
                )
            self._proc = proc
            self._state = {
                "status": "recording",
                "file": out.relative_to(self.tests_root).as_posix(),
                "test_id": fields["id"],
                "title": fields["title"],
                "started_at": now(),
                "log": str(log),
            }
        threading.Thread(target=self._wait, args=(proc, log), daemon=True).start()
        return self.state()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if self._proc is not None and self._proc.stdin is not None:
                try:
                    self._proc.stdin.write(b"\n")
                    self._proc.stdin.flush()
                except OSError:
                    pass  # it has just ended on its own
                self._state["status"] = "saving"
        return self.state()

    def state(self) -> dict[str, Any]:
        with self._lock:
            return {k: v for k, v in self._state.items() if k != "log"}

    def shutdown(self) -> None:
        with self._lock:
            if self._proc is not None:
                self._proc.terminate()

    def _wait(self, proc: subprocess.Popen[bytes], log: Path) -> None:
        code = proc.wait()
        text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
        lines = [ln for ln in text.splitlines() if ln.strip()]
        saved = next((ln for ln in reversed(lines) if ln.startswith("Saved ")), "")
        with self._lock:
            self._proc = None
            self._state.update(finished_at=now(), exit_code=code)
            if code == 0:
                self._state.update(status="saved", message=saved.split(". Replay")[0] or "Saved.")
            else:
                errors = [ln for ln in lines if ln.startswith("error:")]
                message = errors[-1][len("error:") :].strip() if errors else "\n".join(lines[-5:])
                self._state.update(status="error", message=message or f"The recorder stopped with exit code {code}.")
