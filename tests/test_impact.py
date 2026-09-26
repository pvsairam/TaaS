from __future__ import annotations

from conftest import EXAMPLES

from quartermaster.domain.models import ChangeType, Feature, Release
from quartermaster.dsl.loader import load_release, load_tests
from quartermaster.impact.analyzer import analyze, match, plan, severity


def _data() -> tuple[Release, list]:
    return load_release(EXAMPLES / "releases" / "26D_sample.json"), load_tests(EXAMPLES / "tests")


def test_payables_feature_ranks_invoice_test_first() -> None:
    release, tests = _data()
    impacts = analyze(release, tests)
    assert impacts[0].test.id == "ap.create-invoice-po-match"
    assert "FIN-AP-001" in impacts[0].features
    assert any("same product (Payables)" in r for r in impacts[0].reasons)


def test_unrelated_feature_does_not_match() -> None:
    release, tests = _data()
    hcm = next(f for f in release.features if f.id == "HCM-ABS-004")
    for t in tests:
        score, _ = match(hcm, t)
        assert score < 0.15


def test_risk_bounded_and_sorted() -> None:
    release, tests = _data()
    impacts = analyze(release, tests)
    assert all(0 <= i.risk <= 1 for i in impacts)
    assert [i.priority for i in impacts] == sorted((i.priority for i in impacts), reverse=True)


def test_severity_rules() -> None:
    f = Feature(id="F", module="m", product="p", title="t", change_type=ChangeType.UI)
    assert severity(f) == 0.6
    f2 = f.model_copy(update={"customer_action_required": True, "opt_in": True})
    assert severity(f2) == 0.8
    assert abs(severity(f2, {"F"}) - 0.9) < 1e-9
    f3 = f2.model_copy(update={"change_type": ChangeType.BOTH})
    assert severity(f3, {"F"}) == 1.0  # capped


def test_empty_release_has_zero_risk() -> None:
    _, tests = _data()
    impacts = analyze(Release(id="26D"), tests)
    assert all(i.risk == 0 for i in impacts)


def test_plan_respects_budget_but_keeps_critical() -> None:
    release, tests = _data()
    p = plan(analyze(release, tests), budget_minutes=1)
    ids = [i.test.id for i in p.selected]
    assert ids == ["ap.create-invoice-po-match"]  # critical, kept despite 6 min > 1 min budget
    assert len(p.deferred) == 2


def test_plan_without_budget_selects_all_risky() -> None:
    release, tests = _data()
    p = plan(analyze(release, tests))
    assert len(p.selected) == 3
    assert [f.id for f in p.uncovered_features(release)] == ["HCM-ABS-004"]
