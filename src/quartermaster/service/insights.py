"""What the dashboard, test pages and "Needs attention" show, worked out from the run history.

Every finished run points at its suite.json; each suite entry points at a run.json. Nothing here
is stored twice: the numbers are read back from that evidence (cached until the file changes).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from quartermaster.evidence.document import plain_error

_cache: dict[str, tuple[float, Any]] = {}


def read_json(path: Path) -> Any:
    """A JSON file, re-read only when it changes (suite and run records never change once written)."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    key = str(path)
    hit = _cache.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    _cache[key] = (mtime, data)
    return data


def test_results(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per test per finished run, newest run first."""
    rows = []
    for run in runs:
        if not run.get("suite_dir"):
            continue
        suite = read_json(Path(run["suite_dir"]) / "suite.json")
        if not isinstance(suite, dict):
            continue
        for entry in suite.get("runs", []):
            rows.append({**entry, "service_run_id": run["id"], "at": run.get("started_at") or run["created_at"]})
    return rows


def run_counts(run: dict[str, Any]) -> dict[str, int] | None:
    """How many tests of a finished run passed and failed."""
    if not run.get("suite_dir"):
        return None
    suite = read_json(Path(run["suite_dir"]) / "suite.json")
    if not isinstance(suite, dict):
        return None
    statuses = [e.get("status") for e in suite.get("runs", [])]
    passed = sum(s in ("passed", "healed") for s in statuses)
    return {"total": len(statuses), "passed": passed, "failed": len(statuses) - passed}


def dashboard(tests: list[dict[str, Any]], runs: list[dict[str, Any]]) -> dict[str, Any]:
    results = test_results(runs)
    latest: dict[str, dict[str, Any]] = {}
    for r in results:
        latest.setdefault(r["test_id"], r)
    known = {t.get("id") for t in tests if t.get("id")}
    current = {tid: r for tid, r in latest.items() if tid in known}  # tests still in the tests folder
    passing = sum(r["status"] in ("passed", "healed") for r in current.values())
    failing = sum(r["status"] == "failed" for r in current.values())

    finished = [r for r in runs if r.get("suite_dir") and r["status"] in ("passed", "failed")]
    trend = []
    for run in reversed(finished[:20]):  # oldest first, for the chart
        counts = run_counts(run)
        if counts and counts["total"]:
            trend.append({"run_id": run["id"], "at": run.get("started_at"), **counts})

    week_ago = datetime.now().astimezone() - timedelta(days=7)
    this_week = [r for r in runs if _when(r.get("created_at")) >= week_ago]

    modules: dict[str, dict[str, int]] = {}
    for t in tests:
        if t.get("problem"):
            continue
        m = modules.setdefault(t.get("module") or "Other", {"tests": 0, "passing": 0, "failing": 0, "not_run": 0})
        m["tests"] += 1
        last = current.get(t.get("id", ""))
        if last is None:
            m["not_run"] += 1
        elif last["status"] == "failed":
            m["failing"] += 1
        else:
            m["passing"] += 1

    return {
        "tests": len([t for t in tests if not t.get("problem")]),
        "tested": len(current),
        "passing": passing,
        "failing": failing,
        "pass_rate": round(100 * passing / len(current)) if current else None,
        "runs_this_week": len(this_week),
        "tests_run_this_week": sum(1 for r in results if _when(r["at"]) >= week_ago),
        "documents": sum(1 for r in results if r.get("document")),
        "trend": trend,
        "modules": [{"module": k, **v} for k, v in sorted(modules.items())],
        "last_run_at": runs[0].get("started_at") if runs else None,
    }


def test_history(test_id: str, runs: list[dict[str, Any]], evidence_root: Path) -> list[dict[str, Any]]:
    out = []
    for r in test_results(runs):
        if r["test_id"] != test_id:
            continue
        out.append(
            {
                "run_id": r["service_run_id"],
                "at": r["at"],
                "status": r["status"],
                "steps_passed": r.get("steps_passed"),
                "steps_total": r.get("steps_total"),
                "duration": r.get("duration"),
                "document": r.get("document"),
                "folder": r.get("run_dir"),
            }
        )
    return out


def attention(tests: list[dict[str, Any]], runs: list[dict[str, Any]], tests_root: Path) -> dict[str, Any]:
    """Tests that failed last time, tests that passed only because a fallback was used, and unreadable files."""
    by_id = {t["id"]: t for t in tests if t.get("id")}
    latest: dict[str, dict[str, Any]] = {}
    for r in test_results(runs):
        latest.setdefault(r["test_id"], r)

    failing, updates = [], []
    for test_id, r in latest.items():
        test = by_id.get(test_id)
        if test is None:
            continue  # the test file was removed or renamed
        base = {
            "test_id": test_id,
            "title": test.get("title") or test_id,
            "file": test["file"],
            "at": r["at"],
            "run_id": r["service_run_id"],
        }
        if r["status"] == "failed":
            f = r.get("failed_step") or {}
            failing.append(
                {**base, "step": f.get("number"), "intent": f.get("intent"), "error": plain_error(f.get("error"))}
            )
        spec = _load_spec(tests_root / test["file"])
        for h in r.get("healing") or []:
            strategies = _strategies(spec, h.get("step_index", -1))
            new = [str(x) for x in h.get("new") or []]
            if len(new) != 2 or not strategies or strategies[0] == {new[0]: new[1]}:
                continue  # already updated in the file (or the step changed since)
            if {new[0]: new[1]} not in strategies:
                continue
            old = [str(x) for x in h.get("old") or []]
            updates.append(
                {
                    **base,
                    "step_index": h["step_index"],
                    "step": h["step_index"] + 1,
                    "intent": h.get("intent", ""),
                    "old": old,
                    "new": new,
                    "old_text": describe(old),
                    "new_text": describe(new),
                }
            )
    broken = [{"file": t["file"], "problem": t["problem"]} for t in tests if t.get("problem")]
    return {
        "failing": failing,
        "updates": updates,
        "broken": broken,
        "count": len(failing) + len(updates) + len(broken),
    }


def describe(strategy: list[str]) -> str:
    """How a test finds something on the screen, in words a business user can follow."""
    if len(strategy) != 2:
        return ""
    kind, value = strategy
    if kind == "label":
        return f'the field labelled "{value}"'
    if kind == "role" and ":" in value:
        role, name = value.split(":", 1)
        return f'the {role} named "{name}"'
    if kind == "text":
        return f'the text "{value}"'
    if kind == "test_id":
        return f'the element with test id "{value}"'
    return f"a technical page address ({kind})"


def _load_spec(path: Path) -> dict[str, Any]:
    try:
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return spec if isinstance(spec, dict) else {}


def _strategies(spec: dict[str, Any], index: int) -> list[dict[str, str]]:
    steps = spec.get("steps") or []
    if not 0 <= index < len(steps) or not isinstance(steps[index], dict):
        return []
    target = steps[index].get("target") or {}
    found = target.get("strategies") if isinstance(target, dict) else None
    return [{str(k): str(v) for k, v in s.items()} for s in found or [] if isinstance(s, dict)]


def _when(iso: str | None) -> datetime:
    try:
        return datetime.fromisoformat(iso) if iso else datetime.min.replace(tzinfo=datetime.now().astimezone().tzinfo)
    except ValueError:
        return datetime.min.replace(tzinfo=datetime.now().astimezone().tzinfo)
