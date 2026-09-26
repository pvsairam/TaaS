from __future__ import annotations

import pytest
from conftest import EXAMPLES

from quartermaster.cli import main


def test_cli_validate(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(EXAMPLES / "tests")]) == 0
    assert "6 test spec(s) valid" in capsys.readouterr().out


def test_cli_plan(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(
        [
            "plan",
            "--release",
            str(EXAMPLES / "releases" / "26D_sample.json"),
            "--tests",
            str(EXAMPLES / "tests"),
            "--explain",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "ap.create-invoice-po-match" in out
    assert "SCM-OM-007" in out  # reported as uncovered


def test_cli_bad_spec_returns_2(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "x.yaml").write_text("id: [\n")
    assert main(["validate", str(tmp_path)]) == 2
    assert "invalid YAML" in capsys.readouterr().err


def test_cli_run_uses_driver_and_reports(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    from conftest import FakeDriver

    from quartermaster import cli

    monkeypatch.setenv("QM_FUSION_URL", "https://abcd-dev2.fa.us6.oraclecloud.com")
    monkeypatch.setattr(cli, "driver_factory", lambda args: FakeDriver({("text", "Navigator"): 1}))
    report = tmp_path / "r.json"
    rc = main(["run", str(EXAMPLES / "smoke" / "login.yaml"), "--report", str(report)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "HEALED  smoke.login" in out  # role locator missing on fake page, text fallback used
    assert json.loads(report.read_text())[0]["test_id"] == "smoke.login"


def test_cli_run_requires_url(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("QM_FUSION_URL", raising=False)
    assert main(["run", str(EXAMPLES / "smoke")]) == 2
    assert "QM_FUSION_URL" in capsys.readouterr().err


def test_cli_run_refuses_prod_looking_pod(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from conftest import FakeDriver

    from quartermaster import cli

    monkeypatch.setenv("QM_FUSION_URL", "https://abcd.fa.us6.oraclecloud.com")
    monkeypatch.setattr(cli, "driver_factory", lambda args: FakeDriver())
    assert main(["run", str(EXAMPLES / "smoke")]) == 2
    assert "production" in capsys.readouterr().err


def test_cli_run_failure_exit_code(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from conftest import FakeDriver

    from quartermaster import cli

    monkeypatch.setenv("QM_FUSION_URL", "https://abcd-dev2.fa.us6.oraclecloud.com")
    monkeypatch.setattr(cli, "driver_factory", lambda args: FakeDriver())
    assert main(["run", str(EXAMPLES / "smoke")]) == 1
    assert "FAILED  smoke.login" in capsys.readouterr().out
