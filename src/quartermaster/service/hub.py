"""Clients kept apart: one workspace (App) per client, and the web page talks to the one in use.

    first client          the default folders: my_tests, evidence and .qm (what was there before)
    every other client    clients/<name>-<id>/tests and clients/<name>-<id>/evidence, and its run
                          history, manual scripts, schedules and audit log in .qm/clients/<id>

Each workspace has its own tests, manual scripts, evidence, runs, schedules, Needs attention and
audit log, and runs on its own client's pod with its own users, so nothing of one client can turn
up in another's evidence. All workspaces keep running, so every client's schedules run even when
another client is in use. Shared by all: the clients and their pods (environments.db), the
release feature lists, the AI settings and the evidence options.
"""

from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path
from typing import Any

from quartermaster.service.api import App, Reply
from quartermaster.service.environments import Environments
from quartermaster.service.settings import Settings


class Hub:
    def __init__(
        self,
        *,
        tests_root: Path,
        evidence_root: Path,
        data_dir: Path,
        seed_tests: Path | None = None,
        **app_options: Any,
    ):
        self.tests_root = tests_root
        self.evidence_root = evidence_root
        self.data_dir = data_dir
        self.seed_tests = seed_tests  # copied into a new client's tests folder, like the first start
        self._options = app_options
        self.environments = Environments(data_dir / "environments.db")
        old = Settings(data_dir / "settings.json").get()
        self.environments.import_from(os.environ, name=old["environment_name"], release=old["release"])
        self._keys: set[str] = set()  # AI keys pasted in Settings, shared by all clients, in memory only
        self._apps: dict[str, App] = {}
        self._lock = threading.RLock()
        self._started = False

    # ------------------------------------------------------------------ workspaces

    def folders(self, client_id: str) -> tuple[Path, Path, Path]:
        """Tests, evidence and data folders of a client."""
        folder = self.environments.client_folder(client_id) if client_id else ""
        if not folder:  # the first client, or no client set up yet
            return self.tests_root, self.evidence_root, self.data_dir
        base = self.tests_root.resolve().parent / "clients" / folder
        return base / "tests", base / "evidence", self.data_dir / "clients" / client_id

    def _workspace(self, client_id: str) -> App:
        app = self._apps.get(client_id)
        if app is not None:
            return app
        tests, evidence, data = self.folders(client_id)
        if not tests.exists():
            if self.seed_tests and self.seed_tests.is_dir():
                shutil.copytree(self.seed_tests, tests)
            else:
                tests.mkdir(parents=True)
        app = App(
            tests_root=tests,
            evidence_root=evidence,
            data_dir=data,
            environments=self.environments,
            client_id=client_id,
            shared_dir=self.data_dir,
            keys_entered=self._keys,
            **self._options,
        )
        self._apps[client_id] = app
        if self._started:
            app.start()
        return app

    def sync(self) -> None:
        """One workspace per client: start the new ones, stop those of deleted clients."""
        with self._lock:
            wanted = {str(c["id"]) for c in self.environments.clients()} or {""}
            for cid in [c for c in self._apps if c not in wanted]:
                self._apps.pop(cid).stop()  # first, so two workspaces never share the same folders
            for cid in sorted(wanted):
                self._workspace(cid)

    @property
    def app(self) -> App:
        """The workspace of the client in use."""
        with self._lock:
            self.sync()
            return self._workspace(self.environments.active_client_id())

    def workspaces(self) -> dict[str, App]:
        with self._lock:
            self.sync()
            return dict(self._apps)

    # ------------------------------------------------------------------ the web service

    def handle(self, method: str, raw_path: str, body: bytes) -> Reply:
        reply = self.app.handle(method, raw_path, body)
        if method == "POST" and raw_path.startswith("/api/environments"):
            self.sync()  # a client added or deleted
        return reply

    def start(self) -> None:
        with self._lock:
            self.sync()  # made but not started yet
            self._started = True
            for app in self._apps.values():
                app.start()

    def stop(self) -> None:
        with self._lock:
            self._started = False
            for app in self._apps.values():
                app.stop()
