"""Document parsing utilities.

The parser is deterministic and model-free. It currently handles PDF, text,
Markdown, and simple HTML files. PDF extraction uses PyMuPDF when available.
"""

from __future__ import annotations

import csv
import html
import json
import re
from pathlib import Path

from finlongrag.core.schema import Document, PageText


def parse_document(document: Document) -> tuple[Document, list[PageText]]:
    path = document.path_obj
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        pages = _parse_pdf(path, document)
    elif suffix in {".txt", ".md"}:
        pages = _parse_text(path, document)
    elif suffix in {".html", ".htm"}:
        pages = _parse_html(path, document)
    elif suffix == ".csv":
        pages = _parse_csv(path, document)
    elif suffix == ".json":
        pages = _parse_json(path, document)
    elif suffix == ".xlsx":
        pages = _parse_xlsx(path, document)
    else:
        raise ValueError(f"unsupported document type: {path}")

    raw_text = "\n\n".join(page.text for page in pages if page.text)
    parsed = Document(
        doc_id=document.doc_id,
        domain=document.domain,
        title=document.title or _infer_title(raw_text, path.stem),
        path=document.path,
        raw_text=raw_text,
        metadata={**document.metadata, "page_count": len(pages), "parser": "finlongrag.parser"},
    )
    return parsed, pages


def _parse_pdf(path: Path, document: Document) -> list[PageText]:
    try:
        import fitz
    except Exception as exc:
        raise RuntimeError("PyMuPDF is required to parse PDF files") from exc

    pages: list[PageText] = []
    with fitz.open(path) as pdf:
        for index, page in enumerate(pdf, start=1):
            text = _normalize_text(page.get_text("text") or "")
            pages.append(PageText(document.doc_id, document.domain, index, text, {"source": str(path)}))
    return pages


def _parse_text(path: Path, document: Document) -> list[PageText]:
    text = _normalize_text(path.read_text(encoding="utf-8", errors="ignore"))
    return [PageText(document.doc_id, document.domain, 1, text, {"source": str(path)})]


def _parse_html(path: Path, document: Document) -> list[PageText]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    raw = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", raw)
    raw = re.sub(r"(?is)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?is)</p>|</div>|</tr>|</h[1-6]>", "\n", raw)
    text = html.unescape(re.sub(r"(?is)<.*?>", "", raw))
    return [PageText(document.doc_id, document.domain, 1, _normalize_text(text), {"source": str(path)})]


def _parse_csv(path: Path, document: Document) -> list[PageText]:
    rows: list[str] = []
    with path.open("r", encoding="utf-8-sig", errors="ignore", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            rows.append(" | ".join(str(cell).strip() for cell in row if str(cell).strip()))
    text = _normalize_text("\n".join(row for row in rows if row))
    return [PageText(document.doc_id, document.domain, 1, text, {"source": str(path), "format": "csv"})]


def _parse_json(path: Path, document: Document) -> list[PageText]:
    raw = path.read_text(encoding="utf-8-sig", errors="ignore")
    try:
        data = json.loads(raw)
        text = json.dumps(data, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        text = raw
    return [PageText(document.doc_id, document.domain, 1, _normalize_text(text), {"source": str(path), "format": "json"})]


def _parse_xlsx(path: Path, document: Document) -> list[PageText]:
    try:
        from openpyxl import load_workbook
    except Exception as exc:
        raise RuntimeError("openpyxl is required to parse xlsx files") from exc

    workbook = load_workbook(path, read_only=True, data_only=True)
    pages: list[PageText] = []
    try:
        for index, sheet in enumerate(workbook.worksheets, start=1):
            lines: list[str] = [f"# Sheet: {sheet.title}"]
            for row in sheet.iter_rows(values_only=True):
                cells = [str(cell).strip() for cell in row if cell not in (None, "")]
                if cells:
                    lines.append(" | ".join(cells))
            pages.append(
                PageText(
                    document.doc_id,
                    document.domain,
                    index,
                    _normalize_text("\n".join(lines)),
                    {"source": str(path), "format": "xlsx", "sheet": sheet.title},
                )
            )
    finally:
        workbook.close()
    return pages


def _normalize_text(text: str) -> str:
    text = text.replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _infer_title(text: str, default_title: str) -> str:
    for line in text.splitlines()[:20]:
        line = line.strip()
        if len(line) >= 4 and not re.fullmatch(r"(?:第)?\d{1,4}(?:页)?", line):
            return line[:120]
    return default_title
