"""`qm` command line: validate specs and build a risk-ranked regression plan."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from quartermaster.domain.models import Environment, EnvironmentKind, RunResult, ScreenshotMode, StepStatus, TestCase
from quartermaster.dsl.loader import SpecError, load_release, load_test, load_tests
from quartermaster.evidence.document import write_evidence_document
from quartermaster.evidence.run_record import build_record, new_run_id, run_folder, write_record
from quartermaster.evidence.suite import build_suite_record, suite_folder, write_suite_document, write_suite_record
from quartermaster.impact.analyzer import analyze, plan
from quartermaster.runner.credentials import MissingCredentialsError
from quartermaster.runner.engine import Driver, run_test
from quartermaster.safety.guards import UnsafeEnvironmentError, assert_safe_target


def _playwright_driver(args: argparse.Namespace, run_dir: Path) -> Driver:
    from quartermaster.runner.playwright_driver import PlaywrightDriver

    return PlaywrightDriver(headless=not args.headed, evidence_dir=str(run_dir), record_video=args.video != "off")


# Replaced in tests with a fake; the real run drives a browser. Gets the run's evidence folder.
driver_factory: Callable[[argparse.Namespace, Path], Driver] = _playwright_driver


def _validate(args: argparse.Namespace) -> int:
    tests = load_tests(args.tests)
    print(f"OK: {len(tests)} test spec(s) valid in {args.tests}")
    return 0


def _plan(args: argparse.Namespace) -> int:
    release = load_release(args.release)
    tests = load_tests(args.tests)
    opt_ins = set(args.opt_in or [])
    p = plan(analyze(release, tests, opt_ins), budget_minutes=args.budget, min_risk=args.min_risk)

    budget = f"{args.budget:g} min budget" if args.budget else "no budget"
    print(f"Release {release.id}: {len(release.features)} features, {len(tests)} tests, {budget}\n")
    print(f"{'#':>2}  {'priority':>8}  {'risk':>5}  {'min':>4}  test")
    for n, i in enumerate(p.selected, 1):
        print(
            f"{n:>2}  {i.priority:>8.2f}  {i.risk:>5.2f}  {i.test.estimated_minutes:>4g}  {i.test.id} - {i.test.title}"
        )
        if args.explain:
            for r in i.reasons:
                print(f"{'':>26}- {r}")
    print(f"\nSelected {len(p.selected)} test(s), {p.total_minutes:g} min. Deferred {len(p.deferred)}.")
    uncovered = p.uncovered_features(release)
    if uncovered:
        print("\nFeatures with NO covering test (candidates for new tests):")
        for f in uncovered:
            print(f"  - {f.id} [{f.product}] {f.title}")
    return 0


def _run(args: argparse.Namespace) -> int:
    url = os.environ.get("QM_FUSION_URL")
    if not url:
        print("error: set QM_FUSION_URL to the non-prod pod URL", file=sys.stderr)
        return 2
    env = Environment(name=args.env_name, url=url, kind=EnvironmentKind(args.kind), release=args.release)
    target = Path(args.tests)
    if target.is_dir():
        tests: list[TestCase] = load_tests(target)  # also rejects duplicate ids
        files: list[Path] = sorted(target.rglob("*.y*ml"))  # same order load_tests uses
    else:
        tests, files = [load_test(target)], [target]
    evidence_root = Path(args.evidence)
    suite_started = datetime.now().astimezone().isoformat(timespec="seconds")

    results: list[RunResult] = []
    suite_runs: list[tuple[dict[str, Any], Path, Path | None]] = []
    for t, spec_file in zip(tests, files, strict=True):
        run_id = new_run_id()
        run_dir = run_folder(evidence_root, t.id, run_id)
        driver = driver_factory(args, run_dir)
        try:
            result = run_test(t, env, driver, run_id=run_id, screenshots=ScreenshotMode(args.screenshots))
        except (UnsafeEnvironmentError, MissingCredentialsError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        results.append(result)
        print(f"{result.status.value.upper():<7} {t.id}")
        for s in result.steps:
            if s.status in (StepStatus.FAILED, StepStatus.HEALED):
                print(f"        step {s.index + 1} [{s.status.value}] {s.intent}: {s.error or 'used fallback locator'}")

        videos: list[str] = list(getattr(driver, "videos", []))
        if args.video == "on-failure" and result.status is not StepStatus.FAILED:
            for v in videos:
                Path(v).unlink(missing_ok=True)
            videos = []
        record = build_record(result, run_dir=run_dir, test_file=spec_file, video_mode=args.video, videos=videos,
                              executed_by=args.tester)
        write_record(record, run_dir)
        print(f"        evidence: {run_dir}")
        doc: Path | None = None
        if args.evidence_doc:
            doc = write_evidence_document(record, run_dir, run_dir / f"{t.id}_{run_id}_evidence.docx")
            print(f"        document: {doc}")
        suite_runs.append((record, run_dir, doc))

    suite_id = new_run_id()
    suite = build_suite_record(
        suite_runs,
        suite_id=suite_id,
        evidence_root=evidence_root,
        target=str(target),
        started_at=suite_started,
        finished_at=datetime.now().astimezone().isoformat(timespec="seconds"),
    )
    suite_dir = suite_folder(evidence_root, suite_id)
    write_suite_record(suite, suite_dir)
    print(f"\nSuite record: {suite_dir / 'suite.json'}")
    if args.evidence_doc:
        summary = write_suite_document(suite, evidence_root, suite_dir / f"suite_{suite_id}_summary.docx")
        print(f"Summary document: {summary}")

    if args.report:
        Path(args.report).write_text(
            json.dumps([r.model_dump(mode="json") for r in results], indent=2), encoding="utf-8"
        )
    failed = sum(r.status is StepStatus.FAILED for r in results)
    print(f"{len(results) - failed}/{len(results)} passed")
    return 1 if failed else 0


def _document(args: argparse.Namespace) -> int:
    """Rebuild the evidence document from a saved run folder, or the summary from a suite folder."""
    run_dir = Path(args.run_dir)
    if (run_dir / "suite.json").is_file():
        suite = json.loads((run_dir / "suite.json").read_text(encoding="utf-8"))
        # Suite folders live at <evidence root>/_suites/<suite id>/.
        out = Path(args.out) if args.out else run_dir / f"suite_{suite['suite_id']}_summary.docx"
        print(f"Wrote {write_suite_document(suite, run_dir.parent.parent, out)}")
        return 0
    record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    out = Path(args.out) if args.out else run_dir / f"{record['test_id']}_{record['run_id']}_evidence.docx"
    print(f"Wrote {write_evidence_document(record, run_dir, out)}")
    return 0


def _record(args: argparse.Namespace) -> int:
    from quartermaster.recorder.recorder import Recorder, events_to_test, to_yaml
    from quartermaster.runner.playwright_driver import PlaywrightDriver

    url = os.environ.get("QM_FUSION_URL")
    if not url:
        print("error: set QM_FUSION_URL to the non-prod pod URL", file=sys.stderr)
        return 2
    env = Environment(name=args.env_name, url=url, kind=EnvironmentKind(args.kind))
    assert_safe_target(env)

    driver = PlaywrightDriver(headless=False, evidence_dir=args.evidence)
    recorder = Recorder()
    driver.open(env, args.persona)  # sign-in is done for you and never recorded
    try:
        recorder.attach(driver.page)
        print("Recording. Do the business flow in the browser window.")
        print("Use 'Add check' in the page toolbar to record what must be true, e.g. a value on screen.")
        print("Finish with 'Stop recording' in the browser, or press Enter here.")
        _wait_for_stop(recorder, driver.page)
    finally:
        driver.close()

    test = events_to_test(
        recorder.events,
        test_id=args.id,
        title=args.title,
        module=args.module,
        product=args.product,
        persona=args.persona,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(to_yaml(test), encoding="utf-8")
    load_test(out)  # the saved file must pass the same validation as hand-written specs
    print(f"Saved {len(test.steps)} step(s) to {out}. Replay with: qm run {out}")
    return 0


def _wait_for_stop(recorder: Any, page: Any) -> None:
    """Return when Stop recording is pressed in the browser, Enter is pressed here, or the window closes.

    Playwright's sync API may only be used from this thread, so the terminal is read in a helper
    thread while this one keeps the browser responsive.
    """
    entered = threading.Event()
    threading.Thread(target=lambda: (sys.stdin.readline(), entered.set()), daemon=True).start()
    while not (recorder.stopped or entered.is_set()):
        try:
            page.wait_for_timeout(200)  # also delivers the page's events to the recorder
        except Exception:  # the browser window was closed
            return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qm", description="Quartermaster: Oracle Fusion release regression")
    sub = parser.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="validate YAML test specs")
    v.add_argument("tests", help="directory of test specs")
    v.set_defaults(func=_validate)

    pl = sub.add_parser("plan", help="rank tests by release impact")
    pl.add_argument("--release", required=True, help="release feature file (.json/.yaml)")
    pl.add_argument("--tests", required=True, help="directory of test specs")
    pl.add_argument("--budget", type=float, default=None, help="time budget in minutes")
    pl.add_argument("--min-risk", type=float, default=0.05)
    pl.add_argument("--opt-in", action="append", help="feature id enabled in this tenant (repeatable)")
    pl.add_argument("--explain", action="store_true", help="show why each test was selected")
    pl.set_defaults(func=_plan)

    rn = sub.add_parser("run", help="run specs against the pod in QM_FUSION_URL")
    rn.add_argument("tests", help="spec file or directory")
    rn.add_argument("--kind", default=os.environ.get("QM_FUSION_KIND", "DEV"), choices=["DEV", "TEST", "STAGE"])
    rn.add_argument("--env-name", default="fusion")
    rn.add_argument("--headed", action="store_true", help="show the browser window")
    rn.add_argument("--evidence", default="evidence", help="root folder for run evidence (one folder per run)")
    rn.add_argument(
        "--screenshots", default="on-failure", choices=[m.value for m in ScreenshotMode],
        help="when to take screenshots (default: on-failure)",
    )
    rn.add_argument(
        "--video", default="off", choices=["off", "on-failure", "always"],
        help="record a video of the run into the run folder; never put in the document (default: off)",
    )
    rn.add_argument(
        "--evidence-doc", action="store_true",
        help="write a Word evidence document for each test, plus a summary document for the whole run",
    )
    rn.add_argument("--release", help="Oracle release on the pod, e.g. 26C (shown in the evidence)")
    rn.add_argument("--tester", help="name shown as 'Executed by' (default: your login name)")
    rn.add_argument("--report", help="write JSON results for all runs to this file")
    rn.set_defaults(func=_run)

    dc = sub.add_parser("document", help="rebuild a Word document from a saved run or suite folder")
    dc.add_argument("run_dir", help="run folder (run.json) or suite folder (suite.json)")
    dc.add_argument("--out", help="output .docx path (default: inside the run folder)")
    dc.set_defaults(func=_document)

    rc = sub.add_parser("record", help="record a test by clicking through the pod in QM_FUSION_URL")
    rc.add_argument("out", help="YAML file to write")
    rc.add_argument("--id", required=True, help="test id, e.g. hcm.view-worker")
    rc.add_argument("--title", required=True)
    rc.add_argument("--module", required=True, help="e.g. HCM")
    rc.add_argument("--product", required=True, help="e.g. Global Human Resources")
    rc.add_argument("--persona", default="")
    rc.add_argument("--kind", default=os.environ.get("QM_FUSION_KIND", "DEV"), choices=["DEV", "TEST", "STAGE"])
    rc.add_argument("--env-name", default="fusion")
    rc.add_argument("--evidence", default="evidence")
    rc.set_defaults(func=_record)

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (SpecError, UnsafeEnvironmentError, MissingCredentialsError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
