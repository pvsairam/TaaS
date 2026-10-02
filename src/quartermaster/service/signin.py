"""Sign in by hand from Settings, for pods behind single sign-on or MFA.

`qm signin` opens a browser on the pod; the person signs in there. The session it prints is kept
in this process's environment (QM_FUSION_SESSION), never in a file, so the runs, recordings and
Prepare started from here inherit it. It is gone when Quartermaster stops; the pod also ends it
after a while, and then a run says to sign in by hand again.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from quartermaster.runner.session import ENV, PREFIX, SessionError, decode_session


def qm_signin_command() -> list[str]:
    return [sys.executable, "-m", "quartermaster.cli", "signin"]


class SignIn:
    def __init__(self, command: Callable[[], list[str]] = qm_signin_command, cwd: Path | None = None):
        self._command = command
        self._cwd = cwd
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[str] | None = None
        self._state: dict[str, Any] = {"status": "done", "at": None} if os.environ.get(ENV) else {"status": "none"}
        # The variables `qm signin` gets (the active environment's pod); None: this process's own.
        self.environ: Callable[[], dict[str, str]] | None = None

    def view(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                raise ValueError("a sign-in is already waiting in the browser that opened")
            self._proc = subprocess.Popen(
                self._command(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                cwd=self._cwd,
                env=self.environ() if self.environ else None,
            )
            self._state = {"status": "waiting", "at": _now()}
            proc = self._proc
        threading.Thread(target=self._follow, args=(proc,), name="qm-signin", daemon=True).start()
        return self.view()

    def _follow(self, proc: subprocess.Popen[str]) -> None:
        last = ""
        got = False
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if line.startswith(PREFIX):
                text = line[len(PREFIX) :]
                try:
                    decode_session(text)
                except SessionError as e:
                    last = str(e)
                    continue
                os.environ[ENV] = text  # in memory only; the runs started from here inherit it
                got = True
            elif line:
                last = line
        proc.wait()
        with self._lock:
            if self._proc is not proc:
                return  # cancelled, or a newer sign-in
            if got:
                self._state = {"status": "done", "at": _now()}
            else:
                why = last[len("error: ") :] if last.startswith("error: ") else last
                self._state = {"status": "failed", "at": _now(), "error": why or "the sign-in browser closed"}

    def forget(self) -> dict[str, Any]:
        self.stop()
        os.environ.pop(ENV, None)
        with self._lock:
            self._state = {"status": "none"}
        return self.view()

    def stop(self) -> None:
        with self._lock:
            proc, self._proc = self._proc, None
            if self._state.get("status") == "waiting":
                self._state = {"status": "done", "at": None} if os.environ.get(ENV) else {"status": "none"}
        if proc is not None and proc.poll() is None:
            proc.terminate()


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
