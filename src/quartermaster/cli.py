"""`qm` command line: validate specs and build a risk-ranked regression plan."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

from quartermaster.domain.models import Environment, EnvironmentKind, RunResult, StepStatus, TestCase
from quartermaster.dsl.loader import SpecError, load_release, load_test, load_tests
from quartermaster.impact.analyzer import analyze, plan
from quartermaster.runner.credentials import MissingCredentialsError
from quartermaster.runner.engine import Driver, run_test
from quartermaster.safety.guards import UnsafeEnvironmentError


def _playwright_driver(args: argparse.Namespace) -> Driver:
    from quartermaster.runner.playwright_driver import PlaywrightDriver

    return PlaywrightDriver(headless=not args.headed, evidence_dir=args.evidence)


# Replaced in tests with a fake; the real run drives a browser.
driver_factory: Callable[[argparse.Namespace], Driver] = _playwright_driver


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
    env = Environment(name=args.env_name, url=url, kind=EnvironmentKind(args.kind))
    target = Path(args.tests)
    tests: list[TestCase] = load_tests(target) if target.is_dir() else [load_test(target)]

    results: list[RunResult] = []
    for t in tests:
        try:
            result = run_test(t, env, driver_factory(args))
        except (UnsafeEnvironmentError, MissingCredentialsError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        results.append(result)
        print(f"{result.status.value.upper():<7} {t.id}")
        for s in result.steps:
            if s.status in (StepStatus.FAILED, StepStatus.HEALED):
                print(f"        step {s.index} [{s.status.value}] {s.intent}: {s.error or 'used fallback locator'}")

    if args.report:
        Path(args.report).write_text(
            json.dumps([r.model_dump(mode="json") for r in results], indent=2), encoding="utf-8"
        )
    failed = sum(r.status is StepStatus.FAILED for r in results)
    print(f"\n{len(results) - failed}/{len(results)} passed")
    return 1 if failed else 0


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
    rn.add_argument("--evidence", default="evidence", help="directory for failure screenshots")
    rn.add_argument("--report", help="write JSON results to this file")
    rn.set_defaults(func=_run)

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except SpecError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
