"""Release impact for the web UI: the release feature lists on this computer, importing a new one,
and which tests a release puts at risk (the same analysis as `qm plan`).

Release files are read from the releases folder (`qm serve --releases`, by default
examples/releases) and from the imported folder (`.qm/releases`). An imported list with the same
file name as one in the releases folder is the one shown.
"""

from __future__ import annotations

import base64
import binascii
import json
from pathlib import Path
from typing import Any

import yaml

from quartermaster.importers.release_sheet import ImportError_, parse_release
from quartermaster.importers.xlsx import SpreadsheetError

MAX_UPLOAD = 20 * 1024 * 1024
_SUFFIXES = (".json", ".yaml", ".yml")


class Releases:
    def __init__(self, folder: Path | None, imported: Path):
        self.folder = folder.resolve() if folder else None
        self.imported = imported.resolve()

    # ------------------------------------------------------------------ listing

    def _files(self) -> dict[str, tuple[Path, str]]:
        found: dict[str, tuple[Path, str]] = {}
        for root, source in ((self.folder, "folder"), (self.imported, "imported")):  # imported wins
            if root and root.is_dir():
                for f in sorted(root.iterdir()):
                    if f.is_file() and f.suffix.lower() in _SUFFIXES:
                        found[f.name] = (f, source)
        return found

    def list(self) -> list[dict[str, Any]]:
        out = []
        for name, (path, source) in self._files().items():
            item: dict[str, Any] = {"name": name, "source": source, "file": str(path)}
            try:
                data = _read(path)
                features = data.get("features") or []
                item.update(
                    id=str(data.get("id", "")),
                    features=len(features),
                    modules=sorted({str(f.get("module", "")) for f in features if isinstance(f, dict)} - {""}),
                )
            except (OSError, ValueError, yaml.YAMLError) as e:
                item["problem"] = f"Could not read this file: {e}"
            item["updated"] = path.stat().st_mtime
            out.append(item)
        out.sort(key=lambda r: (str(r.get("id", "")), r["updated"]), reverse=True)  # newest release first
        return out

    def path(self, name: str) -> Path:
        hit = self._files().get(name)
        if hit is None:
            raise LookupError(f"no release list named {name!r}")
        return hit[0]

    # ------------------------------------------------------------------ import

    def import_file(self, data: dict[str, Any]) -> dict[str, Any]:
        """{"name", "content" (base64), "release_id", "save"}: read it, and keep it when save is true."""
        name = Path(str(data.get("name") or "")).name
        try:
            content = base64.b64decode(str(data.get("content") or ""), validate=True)
        except (binascii.Error, ValueError) as e:
            raise ValueError("the file did not arrive whole; choose it again") from e
        if not content:
            raise ValueError("choose a file to import")
        if len(content) > MAX_UPLOAD:
            raise ValueError("the file is larger than 20 MB")
        try:
            result = parse_release(name, content, str(data.get("release_id") or ""))
        except (ImportError_, SpreadsheetError) as e:
            raise ValueError(str(e)) from e
        release = result.release
        target = self.imported / f"{release['id']}.json"
        view: dict[str, Any] = {
            "id": release["id"],
            "features": len(release["features"]),
            "sample": release["features"][:8],
            "columns": result.columns,
            "skipped": result.skipped,
            "rows": result.source_rows,
            "name": target.name,
            "replaces": target.name in self._files(),
            "saved": False,
        }
        if data.get("save"):
            self.imported.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(release, indent=2), encoding="utf-8")
            view["saved"] = True
        return view

    # ------------------------------------------------------------------ plan

    def plan(self, name: str, tests_root: Path, budget: float | None, opt_ins: set[str]) -> dict[str, Any]:
        """Which tests to run for this release, why, and which features no test covers."""
        # Imported here so the rest of the service does not need the analysis libraries loaded.
        from quartermaster.domain.models import Priority
        from quartermaster.dsl.loader import SpecError, load_release, load_test
        from quartermaster.impact.analyzer import COVERAGE_THRESHOLD, MATCH_THRESHOLD, analyze, match, plan

        try:
            release = load_release(self.path(name))
        except SpecError as e:
            raise ValueError(f"this release list is not valid: {e}") from e
        tests: list[Any] = []
        files: dict[str, str] = {}
        problems: list[dict[str, str]] = []
        for spec in sorted(tests_root.rglob("*.y*ml")):
            rel = spec.relative_to(tests_root).as_posix()
            try:
                t = load_test(spec)
            except (SpecError, OSError, ValueError) as e:
                problems.append({"file": rel, "problem": str(e).replace(str(spec), rel)[:300]})
                continue
            if t.id in files:
                problems.append({"file": rel, "problem": f"the id {t.id} is also used by {files[t.id]}"})
                continue
            tests.append(t)
            files[t.id] = rel

        impacts = analyze(release, tests, opt_ins)
        result = plan(impacts, budget_minutes=budget)
        chosen = {i.test.id for i in result.selected}
        rows = [
            {
                "id": i.test.id,
                "file": files[i.test.id],
                "title": i.test.title,
                "module": i.test.module,
                "product": i.test.product,
                "priority": i.test.priority.value,
                "minutes": i.test.estimated_minutes,
                "risk": i.risk,
                "score": i.priority,
                "selected": i.test.id in chosen,
                "always": i.test.priority is Priority.CRITICAL,
                "features": i.features,
                "reasons": i.reasons,
            }
            for i in [*result.selected, *sorted(result.deferred, key=lambda i: (-i.priority, -i.risk, i.test.id))]
        ]
        features = []
        for f in release.features:
            scored = sorted(((match(f, t)[0], t.id) for t in tests), reverse=True)
            related = [(round(s, 2), tid) for s, tid in scored if s >= MATCH_THRESHOLD]
            best = related[0][0] if related else 0.0
            features.append(
                {
                    "id": f.id,
                    "title": f.title,
                    "module": f.module,
                    "product": f.product,
                    "change_type": f.change_type.value,
                    "opt_in": f.opt_in,
                    "action_required": f.customer_action_required,
                    "coverage": "covered" if best >= COVERAGE_THRESHOLD else "weak" if related else "none",
                    "tests": [{"id": tid, "match": s} for s, tid in related[:5]],
                }
            )
        counts = {c: sum(f["coverage"] == c for f in features) for c in ("covered", "weak", "none")}
        return {
            "name": name,
            "release": release.id,
            "budget": budget,
            "opt_ins": sorted(opt_ins),
            "tests": rows,
            "features": features,
            "problems": problems,
            "summary": {
                "features": len(features),
                **counts,
                "tests": len(tests),
                "selected": len(result.selected),
                "minutes": result.total_minutes,
                "at_risk": sum(i.risk >= 0.05 for i in impacts),
            },
        }


def _read(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    data = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("not a release list")
    return data
