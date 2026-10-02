"""`qm` command line: validate specs and build a risk-ranked regression plan."""

from __future__ import annotations

import argparse
import json
import os
import queue
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
from quartermaster.safety.guards import UnsafeEnvironmentError, assert_safe_target, confirmed_hosts


def _playwright_driver(args: argparse.Namespace, run_dir: Path) -> Driver:
    from quartermaster.runner.playwright_driver import PlaywrightDriver

    return PlaywrightDriver(
        headless=not args.headed,
        evidence_dir=str(run_dir),
        record_video=args.video != "off",
        highlight=not getattr(args, "no_highlight", False),
    )


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
    if args.only:
        wanted = [t for t in args.only.split(",") if t.strip()]
        unknown = sorted(set(wanted) - {t.id for t in tests})
        if unknown:
            print(f"error: no test with id {', '.join(unknown)} in {target}", file=sys.stderr)
            return 2
        pairs = [(t, f) for t, f in zip(tests, files, strict=True) if t.id in wanted]
        tests, files = [t for t, _ in pairs], [f for _, f in pairs]
    evidence_root = Path(args.evidence)
    suite_started = datetime.now().astimezone().isoformat(timespec="seconds")
    emit = _event_writer(args.events)
    emit({"type": "suite_start", "at": suite_started, "tests": [t.id for t in tests]})

    results: list[RunResult] = []
    suite_runs: list[tuple[dict[str, Any], Path, Path | None]] = []
    for t, spec_file in zip(tests, files, strict=True):
        run_id = new_run_id()
        run_dir = run_folder(evidence_root, t.id, run_id)
        driver = driver_factory(args, run_dir)
        try:
            result = run_test(
                t, env, driver, run_id=run_id, screenshots=ScreenshotMode(args.screenshots), on_event=emit
            )
        except (UnsafeEnvironmentError, MissingCredentialsError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        results.append(result)
        print(f"{result.status.value.upper():<7} {t.id}")
        for s in result.steps:
            if s.status in (StepStatus.FAILED, StepStatus.HEALED):
                print(f"        step {s.index + 1} [{s.status.value}] {s.intent}: {s.error or 'used fallback locator'}")

        for c in result.cleanup:
            if c.status is StepStatus.FAILED:
                print(f"        cleanup {c.index + 1} [failed] {c.intent}: {c.error}")
        if result.cleanup:
            print(f"        cleanup: {result.cleanup_status}")
        videos: list[str] = list(getattr(driver, "videos", []))
        if args.video == "on-failure" and result.status is not StepStatus.FAILED:
            for v in videos:
                Path(v).unlink(missing_ok=True)
            videos = []
        record = build_record(
            result, run_dir=run_dir, test_file=spec_file, video_mode=args.video, videos=videos, executed_by=args.tester
        )
        write_record(record, run_dir)
        print(f"        evidence: {run_dir}")
        doc: Path | None = None
        if args.evidence_doc:
            doc = write_evidence_document(record, run_dir, run_dir / f"{t.id}_{run_id}_evidence.docx")
            print(f"        document: {doc}")
        suite_runs.append((record, run_dir, doc))
        emit(
            {
                "type": "test_saved",
                "test_id": t.id,
                "run_id": run_id,
                "run_dir": str(run_dir),
                "document": str(doc) if doc else None,
                "status": result.status.value,
            }
        )

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
    summary: Path | None = None
    if args.evidence_doc:
        summary = write_suite_document(suite, evidence_root, suite_dir / f"suite_{suite_id}_summary.docx")
        print(f"Summary document: {summary}")
    emit(
        {
            "type": "suite_end",
            "at": suite["finished_at"],
            "status": suite["status"],
            "suite_dir": str(suite_dir),
            "summary": str(summary) if summary else None,
        }
    )

    if args.report:
        Path(args.report).write_text(
            json.dumps([r.model_dump(mode="json") for r in results], indent=2), encoding="utf-8"
        )
    failed = sum(r.status is StepStatus.FAILED for r in results)
    print(f"{len(results) - failed}/{len(results)} passed")
    return 1 if failed else 0


def _event_writer(path: str | None) -> Callable[[dict[str, Any]], None]:
    """Progress events as JSON lines (for the web service); a no-op when no file is given."""
    if not path:
        return lambda _event: None
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)

    def write(event: dict[str, Any]) -> None:
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    return write


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


def _signin(args: argparse.Namespace) -> int:
    """Sign in to the pod by hand (single sign-on, MFA) and print the session for `qm serve`."""
    from quartermaster.runner.playwright_driver import PlaywrightDriver
    from quartermaster.runner.session import PREFIX

    url = os.environ.get("QM_FUSION_URL")
    if not url:
        print("error: set QM_FUSION_URL to the non-prod pod URL", file=sys.stderr)
        return 2
    env = Environment(name="pod", url=url, kind=EnvironmentKind(args.kind))
    assert_safe_target(env, confirmed_hosts())
    driver = PlaywrightDriver(headless=False)
    print("Sign in to the pod in the browser that opened. It closes by itself when the pod's home page shows.")
    try:
        session = driver.sign_in_by_hand(env, timeout_s=args.timeout)
    finally:
        driver.close()
    print(PREFIX + session, flush=True)
    print("Signed in.")
    return 0


def _record(args: argparse.Namespace) -> int:
    from quartermaster.recorder.recorder import Recorder, events_to_test, to_yaml
    from quartermaster.runner.playwright_driver import PlaywrightDriver

    url = os.environ.get("QM_FUSION_URL")
    if not url:
        print("error: set QM_FUSION_URL to the non-prod pod URL", file=sys.stderr)
        return 2
    env = Environment(name=args.env_name, url=url, kind=EnvironmentKind(args.kind))
    assert_safe_target(env, confirmed_hosts())

    driver = PlaywrightDriver(headless=False, evidence_dir=args.evidence)
    recorder = Recorder(feed=Path(args.events) if args.events else None, test_id=args.id)
    run_id = new_run_id()
    if args.guide:  # a manual scenario done by hand: Pass or Fail per step, with a picture each
        from quartermaster.recorder.guided import Guide

        recorder.guide = Guide.load(Path(args.guide), run_folder(Path(args.evidence), args.id, run_id))
        recorder.write_feed()
    driver.open(env, args.persona)  # sign-in is done for you and never recorded
    if args.prepare:  # an AI follows the written steps instead of a person
        return _prepare(args, driver, recorder, env, run_id)
    try:
        recorder.attach(driver.page)
        print("Recording. Do the business flow in the browser window.")
        print("Use 'Add check' in the page toolbar to record what must be true, e.g. a value on screen.")
        print("Finish with 'Stop recording' in the browser, or press Enter here.")
        print("Commands here: pause, resume, check, undo, note <text>, mask (then Enter).")
        _wait_for_stop(recorder, driver.page)
    finally:
        driver.close()

    if recorder.guide is not None:
        return _finish_by_hand(args, recorder, env, run_id)
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
    secrets = [v[6:-1] for v in test.data.values() if v.startswith("${env:")]
    if secrets:
        print("Masked values were not saved. Before running it, set: " + ", ".join(secrets))
    return 0


def _prepare(args: argparse.Namespace, driver: Any, recorder: Any, env: Environment, run_id: str) -> int:
    """Let the AI chosen in Settings do the scenario's steps; save the result as a draft to review."""
    from quartermaster.ai.providers import AIConfig, chat
    from quartermaster.recorder.autopilot import Autopilot

    if recorder.guide is None:
        print("error: --prepare needs --guide (the scenario to prepare)", file=sys.stderr)
        driver.close()
        return 2
    config = AIConfig(args.ai_provider, args.ai_model, args.ai_base_url.rstrip("/"), args.ai_key_env, args.ai_workspace)
    problem = config.problem()
    if problem:
        print(f"error: {problem}", file=sys.stderr)
        driver.close()
        return 2
    lines: queue.Queue[str] = queue.Queue()

    def read_lines() -> None:  # "stop" from the web page ends the preparation
        for line in sys.stdin:
            lines.put(line.strip().lower())

    threading.Thread(target=read_lines, daemon=True).start()

    def should_stop() -> bool:
        while not lines.empty():
            if lines.get() in ("", "stop"):
                return True
        return False

    pilot = Autopilot(
        driver.page,
        recorder.guide,
        recorder,
        ask=lambda system, prompt: chat(config, system, prompt),
        settle=getattr(driver, "_settle", lambda: None),
        should_stop=should_stop,
        navigate=(lambda path: driver.navigate(path, timeout_ms=10_000)) if hasattr(driver, "navigate") else None,
        wait_process=(lambda: driver.wait_job("last", 1800)) if hasattr(driver, "wait_job") else None,
    )
    recorder.message = f"Preparing with {config.label}…"
    recorder.write_feed()
    try:
        finished = pilot.run()
    finally:
        driver.close()
    if not finished:
        print(f"The AI stopped: {pilot.reason}")
    args.tester = f"AI ({config.label})"
    return _finish_by_hand(args, recorder, env, run_id, mode="ai", save_test=finished)


def _finish_by_hand(
    args: argparse.Namespace, recorder: Any, env: Environment, run_id: str, mode: str = "manual", save_test: bool = True
) -> int:
    """Save a manual scenario done by hand: the evidence of what the tester marked (run record, Word
    document, suite record and summary, as for `qm run`), and the clicks as a test that can play by
    itself next time."""
    from quartermaster.recorder.recorder import events_to_test, to_yaml

    guide = recorder.guide
    if not guide.marked:
        print("error: no step was marked Pass or Fail, so nothing was saved", file=sys.stderr)
        return 2
    out: Path | None = Path(args.out)
    if not save_test:
        print("The AI did not finish every step, so no automatic version was saved.")
        out = None
    try:
        if out is None:
            raise ValueError("not saved")
        test = events_to_test(
            recorder.events,
            test_id=args.id,
            title=args.title,
            module=args.module,
            product=args.product,
            persona=args.persona,
            process=args.process or "",
            written_steps=[{"action": s["action"], "expected": s["expected"]} for s in guide.steps],
        )
    except ValueError:
        if out is not None:
            print("No clicks were recorded, so the automatic version was not saved.")
        out = None
    else:
        assert out is not None
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(to_yaml(test), encoding="utf-8")
        load_test(out)
        print(f"Saved {len(test.steps)} step(s) to {out}. Replay with: qm run {out}")

    evidence_root = Path(args.evidence)
    run_dir = guide.run_dir
    result = guide.result(
        test_id=args.id,
        title=args.title,
        environment=env.name,
        environment_url=env.url,
        release=args.release,
        run_id=run_id,
    )
    record = build_record(result, run_dir=run_dir, test_file=out, video_mode="off", videos=[], executed_by=args.tester)
    record["mode"] = mode  # "manual": done by a person, "ai": prepared by an AI; the document says which
    write_record(record, run_dir)
    doc = write_evidence_document(record, run_dir, run_dir / f"{args.id}_{run_id}_evidence.docx")
    suite_id = new_run_id()
    suite = build_suite_record(
        [(record, run_dir, doc)],
        suite_id=suite_id,
        evidence_root=evidence_root,
        target=str(out or args.out),
        started_at=result.started_at or "",
        finished_at=result.finished_at or "",
    )
    suite_dir = suite_folder(evidence_root, suite_id)
    write_suite_record(suite, suite_dir)
    summary = write_suite_document(suite, evidence_root, suite_dir / f"suite_{suite_id}_summary.docx")
    print(f"Evidence document: {doc}")
    print(f"Manual run: {suite_dir}")
    print(f"Summary document: {summary}")
    print(f"Result: {result.status.value}")
    return 0


def _wait_for_stop(recorder: Any, page: Any) -> None:
    """Run the recorder's commands until it stops: Stop recording in the browser, an empty line or
    "stop" here, or the window closing.

    Playwright's sync API may only be used from this thread, so commands are read in a helper
    thread and carried out here, between short waits that keep the browser responsive.
    """
    lines: queue.Queue[str] = queue.Queue()

    def read_lines() -> None:
        while True:
            line = sys.stdin.readline()
            lines.put(line)
            if not line.strip() or line.strip().lower() in ("stop", "finish"):
                return  # an empty line (Enter) or the end of input finishes the recording

    threading.Thread(target=read_lines, daemon=True).start()
    while not recorder.stopped:
        try:
            page.wait_for_timeout(200)  # also delivers the page's events to the recorder
        except Exception:  # the browser window was closed
            return
        while not lines.empty():
            recorder.command(lines.get())


DEFAULT_TESTS = "my_tests"


def _tests_folder(name: str) -> Path | None:
    """The folder `qm serve` keeps tests in. The default one is created on first start with copies of
    the example tests, so what you record, do by hand or prepare never lands among the examples."""
    tests = Path(name)
    examples = Path("examples") / "tests"
    if not tests.is_dir() and name == DEFAULT_TESTS:
        import shutil

        if examples.is_dir():
            shutil.copytree(examples, tests)
        else:
            tests.mkdir(parents=True)
        print(f"Created {tests}: your tests are kept here (it starts with copies of the example tests).")
    if not tests.is_dir():
        print(f"error: no tests folder at {tests}", file=sys.stderr)
        return None
    if examples.is_dir() and tests.resolve() == examples.resolve():
        print(
            "Note: tests you record, do by hand or prepare are saved in this folder, next to the examples. "
            f"Start with `qm serve` (folder {DEFAULT_TESTS}) to keep your own tests apart."
        )
    return tests


def _answers(address: str) -> bool:
    """A Quartermaster answers at this address."""
    import urllib.request

    try:
        with urllib.request.urlopen(f"{address}/api/status", timeout=3) as res:  # noqa: S310 - this computer
            return str(res.headers.get("Server", "")).startswith("Quartermaster")
    except OSError:
        return False


def _ps(path: Path) -> str:
    """A path inside single quotes in PowerShell."""
    return str(path).replace("'", "''")


def _shortcut(args: argparse.Namespace) -> int:
    """Put a Quartermaster icon on the desktop that runs Start Quartermaster.bat (Windows)."""
    start = Path(__file__).resolve().parents[2] / "Start Quartermaster.bat"
    if sys.platform != "win32":
        print("Desktop icons are made on Windows only. Here, start with ./start-quartermaster.sh")
        return 0
    if not start.is_file():
        print(f"error: {start} is missing", file=sys.stderr)
        return 2
    script = (
        "$desktop = [Environment]::GetFolderPath('Desktop'); "
        "$link = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $desktop 'Quartermaster.lnk')); "
        f"$link.TargetPath = '{_ps(start)}'; $link.WorkingDirectory = '{_ps(start.parent)}'; "
        "$link.Description = 'Start Quartermaster'; $link.Save()"
    )
    import subprocess

    done = subprocess.run(["powershell", "-NoProfile", "-Command", script], check=False)
    if done.returncode:
        print("The desktop icon could not be made. Start with 'Start Quartermaster' in the TaaS folder.")
        return 0
    print("Added a Quartermaster icon to the desktop. Double-click it to start Quartermaster.")
    return 0


def _serve(args: argparse.Namespace) -> int:
    import webbrowser

    from quartermaster.service.api import make_server, port_of
    from quartermaster.service.hub import Hub

    address = f"http://127.0.0.1:{args.port}"
    if _answers(address):  # started a second time, e.g. the desktop icon double-clicked again
        print(f"Quartermaster is already running at {address}. Opening it.")
        if not args.no_browser:
            webbrowser.open(address)
        return 0
    # a restore chosen on the Settings page waits for this start: nothing is open yet, so it can be applied
    from quartermaster.service import backup

    waiting = backup.apply_pending(backup.Folders(Path(args.tests), Path(args.evidence), Path(args.data)))
    if waiting:
        print(waiting)
    tests = _tests_folder(args.tests)
    if tests is None:
        return 2
    examples = Path("examples") / "tests"
    # one workspace per client (Settings, Clients and environments); the first client keeps these folders
    app = Hub(
        tests_root=tests,
        evidence_root=Path(args.evidence),
        data_dir=Path(args.data),
        seed_tests=examples if examples.is_dir() else None,
        releases_root=Path(args.releases),
    )
    try:
        server = make_server(app, port=args.port)
    except OSError:
        print(f"error: port {args.port} is used by another program; start with --port 8766", file=sys.stderr)
        app.stop()
        return 2
    address = f"http://127.0.0.1:{port_of(server)}"
    app.start()
    print(f"Quartermaster is running at {address}  (tests: {tests}, evidence: {args.evidence})")
    print("Keep this window open while you use it. Press Ctrl+C to stop.")
    if not args.no_browser:
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping.")
    finally:
        server.server_close()
        app.stop()
    return 0


def _backup(args: argparse.Namespace) -> int:
    from quartermaster.service import backup

    folders = backup.Folders(Path(args.tests), Path(args.evidence), Path(args.data))
    out = Path(args.file)
    try:
        content = backup.create(folders, include_evidence=args.with_evidence)
    except backup.BackupError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(content)
    print(f"Backup saved: {out} ({len(content) // 1024} KB). Test users' passwords are not in it.")
    return 0


def _restore(args: argparse.Namespace) -> int:
    from quartermaster.service import backup

    address = f"http://127.0.0.1:{args.port}"
    if _answers(address):
        print("error: Quartermaster is running. Close it first (or restore from the Settings page).", file=sys.stderr)
        return 2
    folders = backup.Folders(Path(args.tests), Path(args.evidence), Path(args.data))
    try:
        info = backup.restore(folders, Path(args.file).read_bytes())
    except (OSError, backup.BackupError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(
        f"Restored the backup made {info.get('created_at')}. "
        f"The copy of what was here before is in {folders.data / backup.BACKUPS}."
    )
    return 0


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
    rn.add_argument(
        "--no-highlight", action="store_true", help="no red marks on what is clicked or filled (live or in screenshots)"
    )
    rn.add_argument("--evidence", default="evidence", help="root folder for run evidence (one folder per run)")
    rn.add_argument(
        "--screenshots",
        default="on-failure",
        choices=[m.value for m in ScreenshotMode],
        help="when to take screenshots (default: on-failure)",
    )
    rn.add_argument(
        "--video",
        default="off",
        choices=["off", "on-failure", "always"],
        help="record a video of the run into the run folder; never put in the document (default: off)",
    )
    rn.add_argument(
        "--evidence-doc",
        action="store_true",
        help="write a Word evidence document for each test, plus a summary document for the whole run",
    )
    rn.add_argument("--release", help="Oracle release on the pod, e.g. 26C (shown in the evidence)")
    rn.add_argument("--tester", help="name shown as 'Executed by' (default: your login name)")
    rn.add_argument("--report", help="write JSON results for all runs to this file")
    rn.add_argument("--only", help="comma-separated test ids: run just these from the folder")
    rn.add_argument("--events", help="append progress events to this file as JSON lines (used by the web service)")
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
    rc.add_argument("--events", help="keep the steps recorded so far in this file (used by the web UI)")
    rc.add_argument("--guide", help="a manual scenario (JSON) to do by hand, marking each step Pass or Fail")
    rc.add_argument("--process", help="what the test is part of, e.g. Manual scenario ESS-001")
    rc.add_argument("--release", help="Oracle release on the pod, e.g. 26C (shown in the evidence)")
    rc.add_argument("--tester", help="name shown as 'Run by' in the evidence")
    rc.add_argument("--prepare", action="store_true", help="with --guide: an AI does the steps (see Settings)")
    rc.add_argument("--ai-provider", default="", help="AI provider id, e.g. openai, anthropic, openrouter")
    rc.add_argument("--ai-model", default="")
    rc.add_argument("--ai-base-url", default="")
    rc.add_argument("--ai-key-env", default="", help="NAME of the environment variable with the AI key")
    rc.add_argument("--ai-workspace", default="", help="Anthropic only: workspace ID, for a key not tied to one")
    rc.set_defaults(func=_record)

    sc = sub.add_parser("shortcut", help="put a Quartermaster icon on the desktop (Windows)")
    sc.set_defaults(func=_shortcut)

    si = sub.add_parser("signin", help="sign in to the pod by hand (single sign-on, MFA); used by qm serve")
    si.add_argument("--kind", default=os.environ.get("QM_FUSION_KIND", "DEV"), choices=["DEV", "TEST", "STAGE"])
    si.add_argument("--timeout", type=float, default=600, help="seconds to wait for the sign-in")
    si.set_defaults(func=_signin)

    sv = sub.add_parser("serve", help="start the web UI on this computer")
    sv.add_argument(
        "--tests", default=DEFAULT_TESTS, help=f"folder holding your tests ({DEFAULT_TESTS}, created on first start)"
    )
    sv.add_argument("--evidence", default="evidence", help="root folder for run evidence")
    sv.add_argument("--releases", default="examples/releases", help="folder holding release feature lists")
    sv.add_argument("--data", default=".qm", help="folder for the run history and run logs")
    sv.add_argument("--port", type=int, default=8765)
    sv.add_argument("--no-browser", action="store_true", help="do not open the web browser")
    sv.set_defaults(func=_serve)

    for name, func, text in (
        ("backup", _backup, "save your tests, run history, clients and settings in one zip (no passwords)"),
        ("restore", _restore, "put a backup zip back (Quartermaster must not be running)"),
    ):
        bp = sub.add_parser(name, help=text)
        bp.add_argument("file", help="the backup zip" + (" to make" if name == "backup" else " to restore"))
        bp.add_argument("--tests", default=DEFAULT_TESTS, help="your tests folder")
        bp.add_argument("--evidence", default="evidence", help="the evidence folder")
        bp.add_argument("--data", default=".qm", help="the data folder")
        if name == "backup":
            bp.add_argument("--with-evidence", action="store_true", help="also keep screenshots, videos and documents")
        else:
            bp.add_argument("--port", type=int, default=8765)
        bp.set_defaults(func=func)

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (SpecError, UnsafeEnvironmentError, MissingCredentialsError, ValueError, TimeoutError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
