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
