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
            scenarios.extend({k: v for k, v in s.items() if k not in ("cases", "fields")} for s in items)
        return {"files": files, "scenarios": scenarios}

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

    def remove(self, key: str) -> dict[str, Any]:
        if not re.fullmatch(r"[a-z0-9-]+", key or ""):
            raise ValueError("unknown file")
        path = self.folder / f"{key}.json"
        if not path.is_file():
            raise LookupError("that file is not imported")
        path.unlink()
        return {"removed": key}
