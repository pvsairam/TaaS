"""The Word evidence document. Uses only the standard library, like the module under test."""

from __future__ import annotations

import struct
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path
from typing import Any

from quartermaster.evidence.document import write_evidence_document

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def tiny_png(width: int = 16, height: int = 10) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def sample_run(run_dir: Path) -> dict[str, Any]:
    shots = run_dir / "screenshots"
    shots.mkdir(parents=True)
    (shots / "step-01.png").write_bytes(tiny_png())
    (shots / "step-02.png").write_bytes(tiny_png(1600, 1000))
    step = {"duration_ms": 1200.0, "locator": "role=button:Add Location", "started_at": "2026-09-26T19:48:52+00:00"}
    return {
        "schema": 1,
        "run_id": "20260926-194852-5A6C",
        "test_id": "hcm.create-location",
        "test_title": "Fill in a new location up to Submit",
        "status": "failed",
        "environment": "fusion",
        "environment_url": "https://abcd-dev2.fa.us6.oraclecloud.com",
        "release": "26C",
        "persona": "HR Specialist",
        "executed_by": "Test Person",
        "machine": "laptop",
        "started_at": "2026-09-26T19:48:52+00:00",
        "finished_at": "2026-09-26T19:50:40+00:00",
        "screenshots": "every-step",
        "video": "always",
        "videos": ["videos/abc.webm"],
        "test_file": "examples/tests/hcm/create_location.yaml",
        "test_file_sha256": "f" * 64,
        "quartermaster_version": "0.1.0",
        "steps": [
            {**step, "index": 0, "intent": "Click Add Location", "action": "click", "value": None,
             "expected": "New location screen opens (TS002 step 2).", "status": "passed", "error": None,
             "evidence": ["screenshots/step-01.png"]},
            {**step, "index": 1, "intent": "City is filled in", "action": "assert_text", "value": "Redwood City",
             "expected": "", "status": "failed", "error": "StepFailure: expected text 'Redwood City', found ''",
             "evidence": ["screenshots/step-02.png"]},
            {"index": 2, "intent": "Cancel without submitting", "action": "click", "value": None, "expected": "",
             "status": "skipped", "error": None, "evidence": [], "locator": None, "started_at": None,
             "duration_ms": 0},
        ],
        "healing": [],
        "evidence_sha256": {"screenshots/step-01.png": "a" * 64, "screenshots/step-02.png": "b" * 64},
    }


def _open(path: Path) -> tuple[zipfile.ZipFile, str]:
    z = zipfile.ZipFile(path)
    for name in z.namelist():  # every part must be well-formed XML
        if name.endswith((".xml", ".rels")):
            ET.fromstring(z.read(name))
    root = ET.fromstring(z.read("word/document.xml"))
    text = " ".join(t.text or "" for t in root.iter(f"{W}t"))
    return z, text


def test_document_holds_steps_expected_results_and_screenshots(tmp_path: Path) -> None:
    run = sample_run(tmp_path)
    out = write_evidence_document(run, tmp_path, tmp_path / "evidence.docx")
    z, text = _open(out)

    media = [n for n in z.namelist() if n.startswith("word/media/")]
    assert len(media) == 2  # one per screenshot
    for fragment in (
        "Test Evidence Report",
        "FAILED",
        "Step 1: Click Add Location",
        "New location screen opens (TS002 step 2).",  # expected result from the spec
        "The text shows Redwood City.",  # default expected result when the spec has none
        "StepFailure: expected text 'Redwood City', found ''",  # actual result of the failed step
        "Not run, because an earlier step failed.",
        "SHA-256 " + "a" * 64,
        "Reviewed by",
        "videos/abc.webm",
    ):
        assert fragment in text, fragment


def test_videos_are_listed_but_never_embedded(tmp_path: Path) -> None:
    run = sample_run(tmp_path)
    (tmp_path / "videos").mkdir()
    (tmp_path / "videos" / "abc.webm").write_bytes(b"not really a video")
    out = write_evidence_document(run, tmp_path, tmp_path / "evidence.docx")
    z, _ = _open(out)
    assert not any(n.endswith(".webm") for n in z.namelist())
    assert "webm" not in z.read("[Content_Types].xml").decode()


def test_every_relationship_points_at_a_part(tmp_path: Path) -> None:
    out = write_evidence_document(sample_run(tmp_path), tmp_path, tmp_path / "evidence.docx")
    z = zipfile.ZipFile(out)
    names = set(z.namelist())
    rels = ET.fromstring(z.read("word/_rels/document.xml.rels"))
    assert all("word/" + r.get("Target", "") in names for r in rels)
    doc = z.read("word/document.xml").decode()
    ids = {r.get("Id") for r in rels}
    for used in ("rIdFooter", "rIdImg1", "rIdImg2"):
        assert used in ids and used in doc


def test_tall_screenshot_is_scaled_to_fit_the_page(tmp_path: Path) -> None:
    run = sample_run(tmp_path)
    (tmp_path / "screenshots" / "step-01.png").write_bytes(tiny_png(100, 1000))  # 1:10 portrait
    out = write_evidence_document(run, tmp_path, tmp_path / "evidence.docx")
    doc = zipfile.ZipFile(out).read("word/document.xml").decode()
    first = doc.index("<wp:extent")
    cy = int(doc[doc.index('cy="', first) + 4 : doc.index('"', doc.index('cy="', first) + 4)])
    assert cy <= 8 * 914400  # at most 8 inches tall


def test_missing_screenshot_is_reported_not_fatal(tmp_path: Path) -> None:
    run = sample_run(tmp_path)
    (tmp_path / "screenshots" / "step-02.png").unlink()
    _, text = _open(write_evidence_document(run, tmp_path, tmp_path / "evidence.docx"))
    assert "Screenshot missing: screenshots/step-02.png" in text
