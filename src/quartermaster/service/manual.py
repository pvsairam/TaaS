"""Manual test scripts kept on this computer: imported from Excel, listed in the web UI, and matched
to release features alongside the automated tests.

Each imported workbook is kept as one JSON file in the data folder (`.qm/manual`). The workbook
itself is not kept or changed. Importing a workbook with the same file name again replaces it.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from quartermaster.importers.manual_scripts import ScriptError, parse_scripts, slug
from quartermaster.importers.xlsx import SpreadsheetError

MAX_UPLOAD = 20 * 1024 * 1024
MAX_FILES = 50


@dataclass(frozen=True)
class _Step:
    intent: str


@dataclass(frozen=True)
class ManualTest:
    """A manual scenario in the shape release matching reads (see impact.analyzer.Matchable)."""

    id: str
    module: str
    product: str
    title: str
    process: str = ""
    tags: tuple[str, ...] = ()
    steps: tuple[_Step, ...] = field(default=())


class ManualScripts:
    def __init__(self, folder: Path):
        self.folder = folder.resolve()

    def _files(self) -> list[Path]:
        return sorted(self.folder.glob("*.json")) if self.folder.is_dir() else []

    def _load(self, path: Path) -> dict[str, Any] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def scenarios(self) -> list[dict[str, Any]]:
        """Every scenario of every imported workbook, with its cases and steps."""
        out: list[dict[str, Any]] = []
        for path in self._files():
            data = self._load(path)
            if data:
                out.extend(s for s in data.get("scenarios", []) if isinstance(s, dict))
        return out

    def summary(self) -> dict[str, Any]:
        """The list for the web page: scenarios without their steps, and the imported files."""
        files: list[dict[str, Any]] = []
        scenarios: list[dict[str, Any]] = []
        for path in self._files():
            data = self._load(path)
            if not data:
                continue
            items = [s for s in data.get("scenarios", []) if isinstance(s, dict)]
            files.append(
                {
                    "key": path.stem,
                    "file": data.get("file", path.stem),
                    "module": data.get("module", ""),
                    "product": data.get("product", ""),
                    "imported_at": data.get("imported_at"),
                    "scenarios": len(items),
                    "warnings": data.get("warnings", []),
                }
            )
            scenarios.extend(
                {**{k: v for k, v in s.items() if k not in ("cases", "fields")}, "values_missing": values_missing(s)}
                for s in items
            )
        return {"files": files, "scenarios": scenarios}

    @staticmethod
    def test_id(scenario_id: str) -> str:
        """The id of the automated test a scenario becomes once done by hand, e.g. manual.ess-test-script.ess-001."""
        key, _, ref = scenario_id.partition("/")
        return f"manual.{slug(key)}.{slug(ref)}"

    @staticmethod
    def test_file(scenario_id: str) -> str:
        """Where that test is kept, inside the tests folder."""
        key, _, ref = scenario_id.partition("/")
        return f"manual/{slug(key)}/{slug(ref)}.yaml"

    def get(self, scenario_id: str) -> dict[str, Any]:
        for s in self.scenarios():
            if s.get("id") == scenario_id:
                return s
        raise LookupError(f"no manual scenario {scenario_id}")

    def tests(self) -> list[ManualTest]:
        """Scenarios for release matching: the scenario and its test case names, not every step,
        so a long script does not match everything by sheer number of words."""
        return [
            ManualTest(
                id=str(s["id"]),
                module=str(s.get("module", "")),
                product=str(s.get("product", "")),
                title=str(s.get("title", "")),
                process=str(s.get("description", "")),
                steps=tuple(_Step(str(c.get("name", ""))) for c in s.get("cases", [])),
            )
            for s in self.scenarios()
            if s.get("id")
        ]

    def import_files(self, data: dict[str, Any]) -> dict[str, Any]:
        """{"files": [{"name", "content" (base64), "module", "product"}], "save"}: read each workbook,
        and keep them when save is true. One unreadable file does not stop the others."""
        files = data.get("files")
        if not isinstance(files, list) or not files:
            raise ValueError("choose one or more Excel files")
        if len(files) > MAX_FILES:
            raise ValueError(f"import at most {MAX_FILES} files at a time")
        results = []
        for item in files:
            item = item if isinstance(item, dict) else {}
            name = Path(str(item.get("name") or "")).name
            view: dict[str, Any] = {"file": name}
            try:
                content = base64.b64decode(str(item.get("content") or ""), validate=True)
                if len(content) > MAX_UPLOAD:
                    raise ValueError("the file is larger than 20 MB")
                parsed = parse_scripts(name, content, str(item.get("module") or ""), str(item.get("product") or ""))
            except (binascii.Error, ScriptError, SpreadsheetError, ValueError) as e:
                view["problem"] = str(e) if not isinstance(e, binascii.Error) else "the file did not arrive whole"
                results.append(view)
                continue
            key = slug(Path(name).stem)
            target = self.folder / f"{key}.json"
            for s in parsed.scenarios:
                s["id"] = f"{key}/{s['ref']}"  # unique even when two workbooks cover one product
            view.update(
                key=key,
                kind=parsed.kind,
                module=parsed.module,
                product=parsed.product,
                scenarios=len(parsed.scenarios),
                cases=sum(s["case_count"] for s in parsed.scenarios),
                steps=sum(s["step_count"] for s in parsed.scenarios),
                blank_data=sum(bool(s["blank_data"]) for s in parsed.scenarios),
                warnings=parsed.warnings,
                replaces=target.is_file(),
                sample=[s["title"] for s in parsed.scenarios[:5]],
                saved=False,
            )
            if data.get("save") and parsed.module and parsed.product:
                self.folder.mkdir(parents=True, exist_ok=True)
                record = {
                    "file": parsed.file,
                    "kind": parsed.kind,
                    "module": parsed.module,
                    "product": parsed.product,
                    "imported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "warnings": parsed.warnings,
                    "scenarios": parsed.scenarios,
                }
                target.write_text(json.dumps(record, indent=1), encoding="utf-8")
                view["saved"] = True
            results.append(view)
        return {"files": results, "saved": sum(r.get("saved", False) for r in results)}

    # ------------------------------------------------------------------ drafts prepared by AI

    @property
    def _review_file(self) -> Path:
        return self.folder / "_review" / "prepared.json"  # a sub-folder: not read as a workbook

    def reviews(self) -> dict[str, dict[str, Any]]:
        try:
            data = json.loads(self._review_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save_reviews(self, data: dict[str, dict[str, Any]]) -> None:
        self._review_file.parent.mkdir(parents=True, exist_ok=True)
        self._review_file.write_text(json.dumps(data, indent=1), encoding="utf-8")

    def mark_prepared(self, scenario_id: str, run_id: str, by: str) -> None:
        """An AI prepared this scenario: it waits for a person to check its pictures and approve it."""
        data = self.reviews()
        data[scenario_id] = {
            "run_id": run_id,
            "by": by,
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "approved_at": None,
        }
        self._save_reviews(data)

    def approve(self, scenario_id: str) -> dict[str, Any]:
        data = self.reviews()
        if scenario_id not in data:
            raise LookupError("this scenario has no prepared version waiting for review")
        data[scenario_id]["approved_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        self._save_reviews(data)
        return data[scenario_id]

    def checked_by_hand(self, scenario_id: str) -> None:
        """Done by a person: whatever an AI prepared before has been replaced, nothing to review."""
        data = self.reviews()
        if data.pop(scenario_id, None) is not None:
            self._save_reviews(data)

    def remove(self, key: str) -> dict[str, Any]:
        if not re.fullmatch(r"[a-z0-9-]+", key or ""):
            raise ValueError("unknown file")
        path = self.folder / f"{key}.json"
        if not path.is_file():
            raise LookupError("that file is not imported")
        path.unlink()
        return {"removed": key}


_TYPES = re.compile(r"\b(enter|type|fill(?:\s+in)?|input|provide|key\s+in)\b", re.I)
_GIVES = re.compile(r"\d|\bas\s+\S|[:=]\s*\S|\be\.g\.", re.I)


def values_missing(scenario: dict[str, Any]) -> int:
    """How many steps say to type something without saying what ("Enter required data", "enter
    the date"). A person fills those in; the AI never makes values up, so Prepare stops there.
    Names in quotes are usually field names, not values, so they do not count as a value."""
    steps = [st for c in scenario.get("cases") or [] for st in c.get("steps") or []]
    return sum(1 for st in steps if _TYPES.search(st.get("action", "")) and not _GIVES.search(st.get("action", "")))
