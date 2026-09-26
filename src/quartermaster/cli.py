"""`qm` command line: validate specs and build a risk-ranked regression plan."""

from __future__ import annotations

import argparse
import sys

from quartermaster.dsl.loader import SpecError, load_release, load_tests
from quartermaster.impact.analyzer import analyze, plan


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

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except SpecError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
