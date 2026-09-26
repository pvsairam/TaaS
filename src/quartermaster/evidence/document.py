"""Build the Word (.docx) evidence document for one test run.

Input is the run's `run.json` (see `quartermaster.evidence.run_record`), so a document can be
rebuilt at any time from a saved run. Only screenshots go into the document; videos stay in
the run folder and are listed by path.

A .docx file is a zip of XML parts. It is written here with the standard library only, so
producing evidence needs no extra packages.
"""

from __future__ import annotations

import struct
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

# Page: US Letter, 0.75 inch margins. Word measures in twentieths of a point (twips) and
# pictures in EMU (914400 per inch).
_PAGE_W, _PAGE_H, _MARGIN = 12240, 15840, 1080
_TEXT_W = _PAGE_W - 2 * _MARGIN  # 10080 twips = 7 inches
_EMU_PER_INCH = 914400
_MAX_IMG_W_IN, _MAX_IMG_H_IN = 7.0, 8.0

_STATUS_COLOR = {"passed": "2C7A45", "healed": "A45708", "failed": "A63A32", "skipped": "6B7780"}
_STATUS_FILL = {"passed": "E3F1E7", "healed": "F8ECDD", "failed": "F6E3E1", "skipped": "EEF1F3"}
_ACTUAL = {
    "passed": "Completed as expected.",
    "healed": "Completed. The first locator did not match, a backup locator was used.",
    "skipped": "Not run, because an earlier step failed.",
}
_ACTION = {
    "navigate": "Open page",
    "click": "Click",
    "fill": "Enter value",
    "select": "Choose value",
    "assert_visible": "Check it is shown",
    "assert_text": "Check the text",
    "login_as": "Sign in as",
    "wait_job": "Wait for process",
    "api_call": "API call",
}

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def write_evidence_document(run: dict[str, Any], run_dir: Path, out: Path) -> Path:
    """Write the evidence document for `run` (the parsed run.json) to `out`."""
    doc = _Doc(run_dir)
    body = doc.build(run)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _content_types())
        z.writestr("_rels/.rels", _root_rels())
        z.writestr("docProps/core.xml", _core(run))
        z.writestr("word/document.xml", body)
        z.writestr("word/styles.xml", _styles())
        z.writestr("word/footer1.xml", _footer(run))
        z.writestr("word/_rels/document.xml.rels", doc.rels())
        for name, data in doc.media:
            z.writestr(f"word/media/{name}", data)
    return out


# --------------------------------------------------------------------------- document body


class _Doc:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.media: list[tuple[str, bytes]] = []
        self._rels: list[tuple[str, str, str]] = [
            ("rIdStyles", "styles", "styles.xml"),
            ("rIdFooter", "footer", "footer1.xml"),
        ]
        self._pic_id = 0

    def rels(self) -> str:
        base = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
        items = "".join(f'<Relationship Id="{i}" Type="{base}{t}" Target="{target}"/>' for i, t, target in self._rels)
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{items}</Relationships>"
        )

    def build(self, run: dict[str, Any]) -> str:
        steps: list[dict[str, Any]] = run.get("steps", [])
        status = str(run.get("status", "")).lower()
        hashes: dict[str, str] = run.get("evidence_sha256", {})
        parts: list[str] = []
        add = parts.append

        add(_p([_r("Test Evidence Report")], style="Title"))
        add(_p([_r(run.get("test_title") or run.get("test_id", ""))], style="Subtitle"))
        add(
            _p(
                [
                    _r("Result: ", bold=True, size=28),
                    _r(status.upper() or "UNKNOWN", bold=True, size=28, color=_STATUS_COLOR.get(status, "15202A")),
                ],
                after=200,
            )
        )

        add(_p([_r("Run details")], style="Heading1"))
        counts = {k: sum(1 for s in steps if s.get("status") == k) for k in ("passed", "healed", "failed", "skipped")}
        details = [
            ("Test ID", run.get("test_id", "")),
            ("Test title", run.get("test_title", "")),
            ("Test file", run.get("test_file", "")),
            ("Test file SHA-256", run.get("test_file_sha256", "")),
            ("Run ID", run.get("run_id", "")),
            ("Environment", f"{run.get('environment', '')}  {run.get('environment_url', '')}".strip()),
            ("Oracle release", run.get("release") or "Not given"),
            ("Persona", run.get("persona") or "Default user"),
            ("Executed by", run.get("executed_by", "")),
            ("Machine", run.get("machine", "")),
            ("Started", _when(run.get("started_at"))),
            ("Finished", _when(run.get("finished_at"))),
            ("Duration", _duration(run.get("started_at"), run.get("finished_at"))),
            (
                "Steps",
                f"{len(steps)} in total: {counts['passed']} passed, {counts['healed']} passed with a backup locator, "
                f"{counts['failed']} failed, {counts['skipped']} not run",
            ),
            ("Screenshots", _screenshot_setting(run.get("screenshots", ""))),
            ("Video", _video_line(run)),
            ("Quartermaster version", run.get("quartermaster_version", "")),
        ]
        add(_kv_table(details))

        add(_p([_r("Step summary")], style="Heading1"))
        widths = [700, 5680, 1900, 1800]
        rows = [[_cell("#", widths[0], header=True), _cell("Step", widths[1], header=True),
                 _cell("Action", widths[2], header=True), _cell("Result", widths[3], header=True)]]
        for s in steps:
            st = s.get("status", "")
            rows.append([
                _cell(str(s.get("index", 0) + 1), widths[0]),
                _cell(s.get("intent", ""), widths[1]),
                _cell(_ACTION.get(s.get("action", ""), s.get("action", "")), widths[2]),
                _cell(_status_label(st), widths[3], fill=_STATUS_FILL.get(st), color=_STATUS_COLOR.get(st), bold=True),
            ])
        add(_table(rows, widths))

        for s in steps:
            add(_page_break())
            n = s.get("index", 0) + 1
            st = s.get("status", "")
            add(_p([_r(f"Step {n}: {s.get('intent', '')}")], style="Heading2"))
            actual = s.get("error") or _ACTUAL.get(st, "")
            rows_kv = [
                ("Result", _status_label(st)),
                ("Action", _ACTION.get(s.get("action", ""), s.get("action", ""))),
                ("Value used", s.get("value") or "None"),
                ("Expected result", s.get("expected") or _default_expected(s)),
                ("Actual result", actual),
                ("Started", _when(s.get("started_at")) or "Not run"),
                ("Duration", f"{float(s.get('duration_ms', 0)) / 1000:.1f} s" if st != "skipped" else ""),
                ("Element used", s.get("locator") or "None"),
            ]
            add(_kv_table(rows_kv, status_row=("Result", st)))
            shots = s.get("evidence", [])
            if not shots:
                reason = "the step was not run" if st == "skipped" else _screenshot_setting(run.get("screenshots", ""))
                add(_p([_r(f"No screenshot for this step ({reason}).", italic=True, color="6B7780")], before=160))
            for rel in shots:
                add(self._image(rel, n, hashes.get(rel, "")))

        videos = run.get("videos") or []
        healing = run.get("healing") or []
        if videos or healing:
            add(_page_break())
            add(_p([_r("Other evidence")], style="Heading1"))
            if videos:
                add(_p([_r("Video recordings are kept in the run folder and are not part of this document:")]))
                for v in videos:
                    add(_p([_r(v, mono=True)], indent=360))
            if healing:
                add(_p([_r("Locator changes to review (steps that passed with a backup locator):")], before=200))
                for h in healing:
                    old, new = h.get("old", ["", ""]), h.get("new", ["", ""])
                    add(_p([_r(f"Step {h.get('step_index', 0) + 1}: replace {old[0]}={old[1]} with {new[0]}={new[1]}",
                               mono=True)], indent=360))

        add(_page_break())
        add(_p([_r("Sign-off")], style="Heading1"))
        add(_p([_r("By signing, the reviewer confirms this document is a true record of the test run above.")]))
        sw = [2200, 3080, 2800, 2000]
        sign = [[_cell("Role", sw[0], header=True), _cell("Name", sw[1], header=True),
                 _cell("Signature", sw[2], header=True), _cell("Date", sw[3], header=True)]]
        for role, name in (("Executed by", run.get("executed_by", "")), ("Reviewed by", ""), ("Approved by", "")):
            sign.append([_cell(role, sw[0], bold=True), _cell(name, sw[1]), _cell("", sw[2]), _cell("", sw[3])])
        add(_table(sign, sw, row_height=620))

        sect = (
            f'<w:sectPr><w:footerReference w:type="default" r:id="rIdFooter"/>'
            f'<w:pgSz w:w="{_PAGE_W}" w:h="{_PAGE_H}"/>'
            f'<w:pgMar w:top="{_MARGIN}" w:right="{_MARGIN}" w:bottom="{_MARGIN}" w:left="{_MARGIN}" '
            f'w:header="720" w:footer="500" w:gutter="0"/></w:sectPr>'
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:document xmlns:w="{_W}" xmlns:r="{_R}" '
            'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<w:body>{"".join(parts)}{sect}</w:body></w:document>'
        )

    def _image(self, rel: str, step_no: int, sha256: str) -> str:
        path = self.run_dir / rel
        try:
            data = path.read_bytes()
            w_px, h_px = _png_size(data)
        except (OSError, ValueError):
            return _p([_r(f"Screenshot missing: {rel}", italic=True, color="A63A32")])
        self._pic_id += 1
        rid = f"rIdImg{self._pic_id}"
        name = f"image{self._pic_id}.png"
        self.media.append((name, data))
        self._rels.append((rid, "image", f"media/{name}"))
        w_in = _MAX_IMG_W_IN
        h_in = w_in * h_px / w_px
        if h_in > _MAX_IMG_H_IN:
            w_in, h_in = w_in * _MAX_IMG_H_IN / h_in, _MAX_IMG_H_IN
        cx, cy = int(w_in * _EMU_PER_INCH), int(h_in * _EMU_PER_INCH)
        pid = self._pic_id
        drawing = (
            f'<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
            f'<wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="{pid}" name="Screenshot {pid}" '
            f'descr="Screenshot after step {step_no}"/>'
            f'<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<pic:pic><pic:nvPicPr><pic:cNvPr id="{pid}" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
            f'<a:ln w="9525"><a:solidFill><a:srgbClr val="B8C3C9"/></a:solidFill></a:ln></pic:spPr>'
            f'</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>'
        )
        caption = f"Figure {step_no}. Screen after step {step_no}. File {rel}"
        if sha256:
            caption += f", SHA-256 {sha256}"
        return f'<w:p><w:pPr><w:spacing w:before="200" w:after="60"/></w:pPr>{drawing}</w:p>' + _p(
            [_r(caption)], style="Caption"
        )


# --------------------------------------------------------------------------- XML helpers


def _r(
    text: str,
    *,
    bold: bool = False,
    italic: bool = False,
    color: str | None = None,
    size: int | None = None,
    mono: bool = False,
) -> str:
    props = ""
    if mono:
        props += '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/>'
    if bold:
        props += "<w:b/>"
    if italic:
        props += "<w:i/>"
    if color:
        props += f'<w:color w:val="{color}"/>'
    if size:
        props += f'<w:sz w:val="{size}"/>'
    rpr = f"<w:rPr>{props}</w:rPr>" if props else ""
    return f'<w:r>{rpr}<w:t xml:space="preserve">{escape(str(text))}</w:t></w:r>'


def _p(
    runs: list[str], *, style: str | None = None, before: int | None = None, after: int | None = None,
    indent: int | None = None,
) -> str:
    ppr = ""
    if style:
        ppr += f'<w:pStyle w:val="{style}"/>'
    if before is not None or after is not None:
        ppr += "<w:spacing" + (f' w:before="{before}"' if before is not None else "") + (
            f' w:after="{after}"' if after is not None else "") + "/>"
    if indent:
        ppr += f'<w:ind w:left="{indent}"/>'
    return f"<w:p>{f'<w:pPr>{ppr}</w:pPr>' if ppr else ''}{''.join(runs)}</w:p>"


def _page_break() -> str:
    return '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'


def _cell(
    text: str, width: int, *, header: bool = False, fill: str | None = None, color: str | None = None,
    bold: bool = False,
) -> str:
    shade = fill or ("E6EDF0" if header else None)
    tcpr = f'<w:tcW w:w="{width}" w:type="dxa"/>'
    if shade:
        tcpr += f'<w:shd w:val="clear" w:color="auto" w:fill="{shade}"/>'
    run = _r(text, bold=bold or header, color=color, size=18 if header else None)
    return f"<w:tc><w:tcPr>{tcpr}</w:tcPr>{_p([run], after=0)}</w:tc>"


def _table(rows: list[list[str]], widths: list[int], *, row_height: int | None = None) -> str:
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
    border = '<w:{0} w:val="single" w:sz="4" w:space="0" w:color="C9D3D8"/>'
    borders = "".join(border.format(b) for b in ("top", "left", "bottom", "right", "insideH", "insideV"))
    trpr = f'<w:trPr><w:trHeight w:val="{row_height}"/></w:trPr>' if row_height else ""
    header_pr = "<w:trPr><w:tblHeader/></w:trPr>"
    body = "".join(
        f"<w:tr>{header_pr if i == 0 and not row_height else trpr}{''.join(r)}</w:tr>" for i, r in enumerate(rows)
    )
    return (
        f'<w:tbl><w:tblPr><w:tblW w:w="{sum(widths)}" w:type="dxa"/><w:tblBorders>{borders}</w:tblBorders>'
        f'<w:tblLayout w:type="fixed"/><w:tblCellMar><w:top w:w="60" w:type="dxa"/><w:left w:w="100" w:type="dxa"/>'
        f'<w:bottom w:w="60" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar></w:tblPr>'
        f"<w:tblGrid>{grid}</w:tblGrid>{body}</w:tbl>" + _p([], after=120)
    )


def _kv_table(pairs: list[tuple[str, Any]], status_row: tuple[str, str] | None = None) -> str:
    widths = [2600, _TEXT_W - 2600]
    rows = []
    for k, v in pairs:
        if status_row and k == status_row[0]:
            st = status_row[1]
            value = _cell(str(v), widths[1], fill=_STATUS_FILL.get(st), color=_STATUS_COLOR.get(st), bold=True)
        else:
            value = _cell(str(v), widths[1])
        rows.append([_cell(k, widths[0], header=True), value])
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
    border = '<w:{0} w:val="single" w:sz="4" w:space="0" w:color="C9D3D8"/>'
    borders = "".join(border.format(b) for b in ("top", "left", "bottom", "right", "insideH", "insideV"))
    body = "".join(f"<w:tr><w:trPr><w:cantSplit/></w:trPr>{''.join(r)}</w:tr>" for r in rows)
    return (
        f'<w:tbl><w:tblPr><w:tblW w:w="{_TEXT_W}" w:type="dxa"/><w:tblBorders>{borders}</w:tblBorders>'
        f'<w:tblLayout w:type="fixed"/><w:tblCellMar><w:top w:w="50" w:type="dxa"/><w:left w:w="100" w:type="dxa"/>'
        f'<w:bottom w:w="50" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar></w:tblPr>'
        f"<w:tblGrid>{grid}</w:tblGrid>{body}</w:tbl>" + _p([], after=60)
    )


# --------------------------------------------------------------------------- package parts


def _content_types() -> str:
    main = "application/vnd.openxmlformats-officedocument.wordprocessingml"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Default Extension="png" ContentType="image/png"/>'
        f'<Override PartName="/word/document.xml" ContentType="{main}.document.main+xml"/>'
        f'<Override PartName="/word/styles.xml" ContentType="{main}.styles+xml"/>'
        f'<Override PartName="/word/footer1.xml" ContentType="{main}.footer+xml"/>'
        '<Override PartName="/docProps/core.xml" '
        'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        "</Types>"
    )


def _root_rels() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
        'Target="docProps/core.xml"/></Relationships>'
    )


def _core(run: dict[str, Any]) -> str:
    created = run.get("finished_at") or run.get("started_at") or datetime.now().astimezone().isoformat()
    try:
        created_utc = datetime.fromisoformat(created).astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
        created_utc = created_utc[:-2] + ":" + created_utc[-2:]
    except ValueError:
        created_utc = created
    title = escape(f"Test evidence: {run.get('test_title') or run.get('test_id', '')} ({run.get('run_id', '')})")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<dc:title>{title}</dc:title><dc:creator>{escape(str(run.get('executed_by', '')))}</dc:creator>"
        f"<dc:subject>{escape(str(run.get('test_id', '')))}</dc:subject>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{escape(created_utc)}</dcterms:created>'
        "</cp:coreProperties>"
    )


def _footer(run: dict[str, Any]) -> str:
    def field(code: str) -> str:
        return (
            '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            f'<w:r><w:instrText xml:space="preserve"> {code} </w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>1</w:t></w:r>'
            '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
        )

    left = escape(f"{run.get('test_id', '')}  |  Run {run.get('run_id', '')}")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:ftr xmlns:w="{_W}" xmlns:r="{_R}"><w:p><w:pPr><w:pStyle w:val="Footer"/>'
        f'<w:tabs><w:tab w:val="right" w:pos="{_TEXT_W}"/></w:tabs></w:pPr>'
        f'<w:r><w:t xml:space="preserve">{left}</w:t></w:r><w:r><w:tab/></w:r>'
        f'<w:r><w:t xml:space="preserve">Page </w:t></w:r>{field("PAGE")}'
        f'<w:r><w:t xml:space="preserve"> of </w:t></w:r>{field("NUMPAGES")}</w:p></w:ftr>'
    )


def _styles() -> str:
    def para_style(sid: str, name: str, size: int, *, bold: bool = False, color: str = "15202A", before: int = 0,
                   after: int = 120, outline: int | None = None, italic: bool = False) -> str:
        ol = f'<w:outlineLvl w:val="{outline}"/>' if outline is not None else ""
        return (
            f'<w:style w:type="paragraph" w:styleId="{sid}"><w:name w:val="{name}"/><w:basedOn w:val="Normal"/>'
            '<w:next w:val="Normal"/><w:qFormat/>'
            f'<w:pPr><w:keepNext/><w:spacing w:before="{before}" w:after="{after}"/>'
            f'{ol}</w:pPr><w:rPr>{"<w:b/>" if bold else ""}{"<w:i/>" if italic else ""}'
            f'<w:color w:val="{color}"/><w:sz w:val="{size}"/></w:rPr></w:style>'
        )

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:styles xmlns:w="{_W}">'
        '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri" '
        'w:eastAsia="Calibri"/><w:sz w:val="20"/><w:szCs w:val="20"/><w:lang w:val="en-US"/></w:rPr></w:rPrDefault>'
        '<w:pPrDefault><w:pPr><w:spacing w:after="80" w:line="264" w:lineRule="auto"/></w:pPr></w:pPrDefault>'
        "</w:docDefaults>"
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/>'
        '<w:rPr><w:color w:val="15202A"/></w:rPr></w:style>'
        + para_style("Title", "Title", 44, bold=True, color="0E6B70", after=60)
        + para_style("Subtitle", "Subtitle", 28, color="3F4B55", after=160)
        + para_style("Heading1", "heading 1", 28, bold=True, color="0E6B70", before=280, after=120, outline=0)
        + para_style("Heading2", "heading 2", 24, bold=True, before=0, after=120, outline=1)
        + para_style("Caption", "caption", 16, color="56646F", after=120, italic=True)
        + para_style("Footer", "footer", 16, color="56646F", after=0)
        + "</w:styles>"
    )


# --------------------------------------------------------------------------- small helpers


def _png_size(data: bytes) -> tuple[int, int]:
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("not a PNG file")
    w, h = struct.unpack(">II", data[16:24])
    if not w or not h:
        raise ValueError("empty PNG")
    return w, h


def _when(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %Y, %H:%M:%S %Z").strip().rstrip(",")
    except ValueError:
        return iso


def _duration(start: str | None, end: str | None) -> str:
    try:
        secs = (datetime.fromisoformat(end or "") - datetime.fromisoformat(start or "")).total_seconds()
    except ValueError:
        return ""
    m, s = divmod(int(round(secs)), 60)
    return f"{m} min {s} s" if m else f"{s} s"


def _status_label(status: str) -> str:
    return {"passed": "Passed", "healed": "Passed (backup locator)", "failed": "Failed", "skipped": "Not run"}.get(
        status, status
    )


def _screenshot_setting(mode: str) -> str:
    return {
        "every-step": "taken after every step",
        "on-failure": "taken only when a step fails",
        "off": "switched off for this run",
    }.get(mode, mode)


def _video_line(run: dict[str, Any]) -> str:
    videos = run.get("videos") or []
    mode = run.get("video", "off")
    if videos:
        return f"Recorded, {len(videos)} file(s) in the run folder (listed at the end)"
    if mode == "on-failure":
        return "Recorded only on failure; this run passed, so none was kept"
    return "Not recorded"


def _default_expected(step: dict[str, Any]) -> str:
    action, value = step.get("action", ""), step.get("value") or ""
    return {
        "navigate": "The page opens.",
        "click": "The click is accepted and the next screen or state appears.",
        "fill": f"The field accepts the value {value}." if value else "The field accepts the value.",
        "select": f"{value} is chosen." if value else "The value is chosen.",
        "assert_visible": "The item is shown on the screen.",
        "assert_text": f"The text shows {value}." if value else "The expected text is shown.",
        "login_as": f"Signed in as {value}." if value else "Signed in.",
    }.get(action, "The step completes.")
