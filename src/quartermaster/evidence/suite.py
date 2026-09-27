"""One summary for a whole `qm run`: suite.json and, on request, a summary Word document.

    evidence/_suites/<suite id>/
        suite.json                        every test's result and where its evidence is
        suite_<suite id>_summary.docx     the summary document (with --evidence-doc, 2+ tests)

Each test keeps its own run folder and evidence document; the summary points to them by path
relative to the evidence root, so the whole evidence folder can be moved or zipped.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quartermaster.evidence.document import (
    _STATUS_COLOR,
    _STATUS_FILL,
    _TEXT_W,
    _cell,
    _Doc,
    _duration,
    _kv_table,
    _p,
    _page_break,
    _r,
    _screenshot_setting,
    _status_label,
    _table,
    _when,
    document_xml,
    write_package,
)

SCHEMA_VERSION = 1
SUITES_FOLDER = "_suites"


def suite_folder(evidence_root: Path, suite_id: str) -> Path:
    return evidence_root / SUITES_FOLDER / suite_id


def build_suite_record(
    runs: list[tuple[dict[str, Any], Path, Path | None]],
    *,
    suite_id: str,
    evidence_root: Path,
    target: str,
    started_at: str,
    finished_at: str,
) -> dict[str, Any]:
    """`runs` holds (run record, run folder, evidence document or None) for each test, in run order."""
    entries = [_entry(record, run_dir, doc, evidence_root) for record, run_dir, doc in runs]
    first = runs[0][0] if runs else {}
    return {
        "schema": SCHEMA_VERSION,
        "suite_id": suite_id,
        "status": _overall([e["status"] for e in entries]),
        "target": target,
        "environment": first.get("environment", ""),
        "environment_url": first.get("environment_url", ""),
        "release": first.get("release"),
        "executed_by": first.get("executed_by", ""),
        "machine": first.get("machine", ""),
        "screenshots": first.get("screenshots", ""),
        "video": first.get("video", ""),
        "quartermaster_version": first.get("quartermaster_version", ""),
        "started_at": started_at,
        "finished_at": finished_at,
        "runs": entries,
    }


def write_suite_record(suite: dict[str, Any], suite_dir: Path) -> Path:
    suite_dir.mkdir(parents=True, exist_ok=True)
    out = suite_dir / "suite.json"
    out.write_text(json.dumps(suite, indent=2), encoding="utf-8")
    return out


def write_suite_document(suite: dict[str, Any], evidence_root: Path, out: Path) -> Path:
    doc = _Doc(evidence_root)  # screenshots are referenced relative to the evidence root
    runs: list[dict[str, Any]] = suite.get("runs", [])
    status = suite.get("status", "")
    parts: list[str] = []
    add = parts.append

    add(_p([_r("Regression Run Summary")], style="Title"))
    release = f"Oracle release {suite['release']}" if suite.get("release") else "Oracle release not given"
    add(_p([_r(f"{len(runs)} test(s) from {suite.get('target', '')}, {release}")], style="Subtitle"))
    add(_p([_r("Result: ", bold=True, size=28), _r(_overall_label(status), bold=True, size=28,
                                                     color=_STATUS_COLOR.get(status, "15202A"))], after=200))

    counts = {k: sum(1 for r in runs if r["status"] == k) for k in ("passed", "healed", "failed")}
    add(_p([_r("Run details")], style="Heading1"))
    add(_kv_table([
        ("Suite run ID", suite.get("suite_id", "")),
        ("Tests", f"{len(runs)} in total: {counts['passed']} passed, {counts['healed']} passed with a backup "
                  f"locator, {counts['failed']} failed"),
        ("Tests from", suite.get("target", "")),
        ("Environment", f"{suite.get('environment', '')}  {suite.get('environment_url', '')}".strip()),
        ("Oracle release", suite.get("release") or "Not given"),
        ("Executed by", suite.get("executed_by", "")),
        ("Machine", suite.get("machine", "")),
        ("Started", _when(suite.get("started_at"))),
        ("Finished", _when(suite.get("finished_at"))),
        ("Duration", _duration(suite.get("started_at"), suite.get("finished_at"))),
        ("Screenshots", _screenshot_setting(suite.get("screenshots", ""))),
        ("Video", {"always": "Recorded for every test", "on-failure": "Kept for failed tests only"}.get(
            suite.get("video", ""), "Not recorded")),
        ("Quartermaster version", suite.get("quartermaster_version", "")),
    ]))

    add(_p([_r("Results")], style="Heading1"))
    widths = [500, 5180, 2000, 1200, 1200]
    rows = [[_cell(h, w, header=True) for h, w in zip(("#", "Test", "Result", "Steps", "Duration"), widths)]]
    for n, r in enumerate(runs, 1):
        st = r["status"]
        rows.append([
            _cell(str(n), widths[0]),
            _cell(f"{r.get('test_title') or r['test_id']} ({r['test_id']})", widths[1]),
            _cell(_status_label(st), widths[2], fill=_STATUS_FILL.get(st), color=_STATUS_COLOR.get(st), bold=True),
            _cell(f"{r['steps_passed']} of {r['steps_total']}", widths[3]),
            _cell(r.get("duration", ""), widths[4]),
        ])
    add(_table(rows, widths))

    add(_p([_r("Where the evidence is")], style="Heading1"))
    add(_p([_r("Paths are relative to the evidence folder. Each test's document holds its step-by-step proof.")]))
    ew = [3000, _TEXT_W - 3000]
    erows = [[_cell("Test", ew[0], header=True), _cell("Evidence document, or run folder", ew[1], header=True)]]
    for r in runs:
        erows.append([_cell(r["test_id"], ew[0]), _cell(r.get("document") or r["run_dir"], ew[1])])
    add(_table(erows, ew))

    failed = [r for r in runs if r["status"] == "failed"]
    for r in failed:
        add(_page_break())
        f = r.get("failed_step") or {}
        add(_p([_r(f"Failed: {r.get('test_title') or r['test_id']}")], style="Heading2"))
        add(_kv_table([
            ("Result", _status_label("failed")),
            ("Failed step", f"Step {f.get('number', '?')}: {f.get('intent', '')}"),
            ("Error", f.get("error") or ""),
            ("Steps not run", str(r["steps_total"] - r["steps_passed"] - 1)),
            ("Evidence", r.get("document") or r["run_dir"]),
        ], status_row=("Result", "failed")))
        if f.get("screenshot"):
            add(doc._image(f["screenshot"], int(f.get("number", 0)), "",
                           caption=f"Screen when step {f.get('number')} failed. File {f['screenshot']}"))

    healed = [(r, h) for r in runs for h in r.get("healing", [])]
    if healed:
        add(_p([_r("Locator changes to review")], style="Heading1"))
        add(_p([_r("These steps passed with a backup locator. Update the test so the first locator matches again:")]))
        for r, h in healed:
            old, new = h.get("old", ["", ""]), h.get("new", ["", ""])
            add(_p([_r(f"{r['test_id']}, step {h.get('step_index', 0) + 1}: replace {old[0]}={old[1]} "
                       f"with {new[0]}={new[1]}", mono=True)], indent=360))

    add(_page_break())
    add(_p([_r("Sign-off")], style="Heading1"))
    add(_p([_r("By signing, the reviewer confirms this summary and the evidence documents it lists are a true "
               "record of the regression run above.")]))
    sw = [2200, 3080, 2800, 2000]
    sign = [[_cell(h, w, header=True) for h, w in zip(("Role", "Name", "Signature", "Date"), sw)]]
    for role, name in (("Executed by", suite.get("executed_by", "")), ("Reviewed by", ""), ("Approved by", "")):
        sign.append([_cell(role, sw[0], bold=True), _cell(name, sw[1]), _cell("", sw[2]), _cell("", sw[3])])
    add(_table(sign, sw, row_height=620))

    return write_package(
        out,
        doc,
        document_xml(parts),
        title=f"Regression run summary ({suite.get('suite_id', '')})",
        creator=str(suite.get("executed_by", "")),
        subject=str(suite.get("target", "")),
        created=suite.get("finished_at") or suite.get("started_at"),
        footer_left=f"Regression run {suite.get('suite_id', '')}",
    )


def _entry(record: dict[str, Any], run_dir: Path, doc: Path | None, evidence_root: Path) -> dict[str, Any]:
    steps: list[dict[str, Any]] = record.get("steps", [])
    failed = next((s for s in steps if s.get("status") == "failed"), None)
    entry: dict[str, Any] = {
        "test_id": record.get("test_id", ""),
        "test_title": record.get("test_title", ""),
        "status": record.get("status", ""),
        "run_id": record.get("run_id", ""),
        "run_dir": _relative(run_dir, evidence_root),
        "document": _relative(doc, evidence_root) if doc else None,
        "steps_total": len(steps),
        "steps_passed": sum(1 for s in steps if s.get("status") in ("passed", "healed")),
        "duration": _duration(record.get("started_at"), record.get("finished_at")),
        "failed_step": None,
        "healing": record.get("healing", []),
    }
    if failed:
        shots = failed.get("evidence") or []
        entry["failed_step"] = {
            "number": failed.get("index", 0) + 1,
            "intent": failed.get("intent", ""),
            "error": failed.get("error"),
            "screenshot": _relative(run_dir / shots[0], evidence_root) if shots else None,
        }
    return entry


def _overall(statuses: list[str]) -> str:
    if "failed" in statuses:
        return "failed"
    if "healed" in statuses:
        return "healed"
    return "passed" if statuses else ""


def _overall_label(status: str) -> str:
    return {"passed": "ALL PASSED", "healed": "ALL PASSED (some with backup locators)", "failed": "FAILURES"}.get(
        status, status.upper() or "NO TESTS"
    )


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
