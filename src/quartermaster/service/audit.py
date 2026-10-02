"""The audit log: who did what in Quartermaster, and when.

Every change made through the web service is added as one line to `.qm/audit.jsonl`: runs started
and cancelled, approvals, accepted screen changes, test data saved, imports, schedules, settings
and sign-ins. Lines are only ever added. Secrets never go in: not the AI key, not the sign-in done
by hand, not the test data values (only which steps were changed).

"Who" is the person named in the request when there is one (the tester of a run by hand), else the
user signed in to this computer, since Quartermaster has no log-in of its own.
"""

from __future__ import annotations

import csv
import getpass
import io
import json
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

MAX_SHOWN = 1000

Described = tuple[str, str, dict[str, Any]]  # what was done, to what, details


def computer_user() -> str:
    try:
        return getpass.getuser()
    except Exception:  # no user name on this computer (some containers)
        return "unknown"


class AuditLog:
    def __init__(self, path: Path, who: Callable[[], str] = computer_user):
        self.path = path
        self._who = who
        self._lock = threading.Lock()

    def add(self, action: str, subject: str, details: dict[str, Any] | None = None, who: str = "") -> None:
        entry = {
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "who": who or self._who(),
            "action": action,
            "subject": subject,
            "details": {k: v for k, v in (details or {}).items() if v not in (None, "", [], {})},
        }
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

    def entries(self, limit: int = MAX_SHOWN) -> list[dict[str, Any]]:
        """Newest first."""
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out: list[dict[str, Any]] = []
        for line in reversed(lines):
            try:
                item = json.loads(line)
            except ValueError:
                continue  # a line cut short when the computer stopped
            if isinstance(item, dict):
                out.append(item)
            if len(out) >= limit:
                break
        return out

    def as_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["When", "Who", "What", "Subject", "Details"])
        for e in reversed(self.entries(limit=10**9)):  # oldest first, like a ledger
            details = "; ".join(f"{k}: {_text(v)}" for k, v in (e.get("details") or {}).items())
            w.writerow([e.get("at", ""), e.get("who", ""), e.get("action", ""), e.get("subject", ""), details])
        return buf.getvalue()


def _target(target: Any) -> str:
    return "All tests" if str(target or ".") == "." else str(target)


def _text(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def describe(route: list[str], data: dict[str, Any], reply: Any) -> Described | None:
    """How a successful POST to /api/<route> reads in the log, or None when it changes nothing."""
    reply = reply if isinstance(reply, dict) else {}
    key = "/".join(route)
    given = data.get("options")
    options: dict[str, Any] = given if isinstance(given, dict) else {}
    if key == "settings":
        return "Changed settings", "Settings", {k: v for k, v in data.items() if isinstance(v, str | int | bool)}
    if key == "ai/key":
        return ("Entered the AI key" if str(data.get("key") or "").strip() else "Removed the AI key"), "AI", {}
    if key == "signin":
        return "Opened a browser to sign in by hand", "Sign-in", {}
    if key == "signin/forget":
        return "Forgot the sign-in done by hand", "Sign-in", {}
    if key == "test/accept-update":
        return (
            "Accepted an Oracle screen change",
            str(data.get("file") or ""),
            {
                "step": int(data.get("step_index", -1)) + 1,
                "now finds it by": " ".join(str(x) for x in data.get("new") or []),
            },
        )
    if key == "runs":
        return (
            "Started a run",
            _target(data.get("target")),
            {
                "run": reply.get("id"),
                "release": (reply.get("options") or {}).get("release"),
                "label": options.get("label"),
            },
        )
    if len(route) == 3 and route[0] == "runs" and route[2] == "cancel":
        return "Cancelled a run", route[1], {}
    if key == "recording":
        return (
            "Started recording a test",
            str(data.get("title") or data.get("out") or ""),
            {"module": data.get("module")},
        )
    if key == "releases/import" and data.get("save"):
        return "Imported a release feature list", str(data.get("name") or ""), {}
    if key == "schedules":
        return (
            ("Changed a schedule" if data.get("id") else "Added a schedule"),
            str(reply.get("name") or ""),
            {
                "what": _target(reply.get("target")),
                "when": reply.get("when"),
                "on": "yes" if reply.get("enabled") else "no",
            },
        )
    if key == "schedules/delete":
        return "Deleted a schedule", str(data.get("id") or ""), {}
    if key == "schedules/run":
        return "Started a schedule now", str(data.get("id") or ""), {"run": reply.get("id")}
    if key == "manual/data":
        raw = data.get("values")
        values: dict[str, Any] = raw if isinstance(raw, dict) else {}
        return (
            "Saved test data",
            str(data.get("id") or ""),
            {"steps": sorted(values, key=lambda n: int(n) if str(n).isdigit() else 0)},
        )
    if key == "manual/run":
        how = "Prepare (AI)" if data.get("prepare") else "by hand" if data.get("by_hand") else "by itself"
        return "Ran a manual scenario", str(data.get("id") or ""), {"how": how, "tester": data.get("tester")}
    if key == "manual/approve":
        listed = data.get("ids")
        ids: list[Any] = listed if isinstance(listed, list) else [data.get("id")]
        return "Approved what the AI prepared", ", ".join(str(i) for i in ids), {}
    if key == "manual/prepare-all":
        return "Started Prepare all", "Manual scenarios", {"scenarios": reply.get("total")}
    if key == "manual/prepare-all/stop":
        return "Stopped Prepare all", "Manual scenarios", {}
    if key == "manual/import" and data.get("save"):
        files = [r.get("file") for r in reply.get("files") or [] if isinstance(r, dict) and r.get("saved")]
        return "Imported manual scripts", ", ".join(str(f) for f in files), {}
    if key == "manual/remove":
        return "Removed imported manual scripts", str(data.get("key") or ""), {}
    if key == "manual/typed":
        return (
            ("Changed a typed scenario" if data.get("id") else "Typed a new scenario"),
            str(reply.get("id") or ""),
            {
                "title": reply.get("title"),
                "steps": reply.get("step_count"),
            },
        )
    if key == "manual/typed/delete":
        return "Deleted a typed scenario", str(data.get("id") or ""), {}
    return None
