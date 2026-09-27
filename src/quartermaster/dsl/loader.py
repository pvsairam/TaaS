"""Load and validate YAML test specs and release feature files."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import yaml
from pydantic import ValidationError

from quartermaster.domain.models import Release, TestCase


class SpecError(ValueError):
    """A spec file failed to parse or validate. Message names the file."""


_PLACEHOLDER = re.compile(r"\$\{((?:env:)?[A-Za-z_][A-Za-z0-9_]*)\}")

# Values the runner supplies at execution time, e.g. a unique suffix for document numbers.
RUNTIME_VARS = frozenset({"RUN_ID"})

# ${env:NAME} reads a masked value (one that must not be written in the test file) from the
# environment variable NAME when the test runs; evidence shows it as MASK.
SECRET = "env:"
MASK = "••••••"


class MissingSecretError(ValueError):
    """A masked value's environment variable is not set on this computer."""


def _read_yaml(path: Path) -> object:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise SpecError(f"{path}: invalid YAML: {e}") from e


def load_test(path: str | Path) -> TestCase:
    path = Path(path)
    raw = _read_yaml(path)
    try:
        test = TestCase.model_validate(raw)
    except ValidationError as e:
        raise SpecError(f"{path}: {e}") from e
    _check_placeholders(test, path)
    return test


def load_tests(directory: str | Path) -> list[TestCase]:
    directory = Path(directory)
    tests = [load_test(p) for p in sorted(directory.rglob("*.y*ml"))]
    seen: dict[str, int] = {}
    for t in tests:
        seen[t.id] = seen.get(t.id, 0) + 1
    dupes = sorted(k for k, n in seen.items() if n > 1)
    if dupes:
        raise SpecError(f"{directory}: duplicate test ids: {', '.join(dupes)}")
    return tests


def load_release(path: str | Path) -> Release:
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8")) if path.suffix == ".json" else _read_yaml(path)
    try:
        return Release.model_validate(raw)
    except ValidationError as e:
        raise SpecError(f"{path}: {e}") from e


def _check_placeholders(test: TestCase, path: Path) -> None:
    """Every ${name} must be declared in the test's `data` block or be a runtime variable."""
    known = set(test.data) | RUNTIME_VARS
    for key, val in test.data.items():
        for name in _PLACEHOLDER.findall(val):
            if name not in RUNTIME_VARS and not name.startswith(SECRET):
                raise SpecError(f"{path}: data '{key}' may only reference runtime variables, not ${{{name}}}")
    for i, step in enumerate(test.steps):
        texts = [step.value or ""] + [v for _, v in (step.target.ordered() if step.target else [])]
        for name in (n for t in texts for n in _PLACEHOLDER.findall(t)):
            if name not in known and not name.startswith(SECRET):
                raise SpecError(f"{path}: step {i} uses undefined data placeholder ${{{name}}}")


def render_value(value: str | None, data: dict[str, str], runtime: dict[str, str] | None = None) -> str | None:
    """Substitute ${name} from test data, then runtime variables (data may reference those)."""
    if value is None:
        return None
    return _PLACEHOLDER.sub(_from_environment, _substitute(value, data, runtime))


def display_value(value: str | None, data: dict[str, str], runtime: dict[str, str] | None = None) -> str | None:
    """The value as evidence may show it: like render_value, but masked values stay hidden."""
    if value is None:
        return None
    return _PLACEHOLDER.sub(
        lambda m: MASK if m.group(1).startswith(SECRET) else m.group(0), _substitute(value, data, runtime)
    )


def _substitute(value: str, data: dict[str, str], runtime: dict[str, str] | None) -> str:
    runtime = runtime or {}
    value = _PLACEHOLDER.sub(lambda m: data.get(m.group(1), m.group(0)), value)
    return _PLACEHOLDER.sub(lambda m: runtime.get(m.group(1), m.group(0)), value)


def _from_environment(m: re.Match[str]) -> str:
    name = m.group(1)
    if not name.startswith(SECRET):
        return m.group(0)
    var = name[len(SECRET) :]
    if var not in os.environ:
        raise MissingSecretError(f"this test types a masked value: set the environment variable {var} first")
    return os.environ[var]
