"""Structure-aware chunking for long documents."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from finlongrag.core.schema import Chunk, Document, PageText

NUMBER_RE = re.compile(r"[-+]?(?:\d{1,3}(?:[,，]\d{3})+|\d+)(?:\.\d+)?\s*(?:%|％|元|万元|亿元|万|亿|倍|天|日|月|年)?")
DATE_RE = re.compile(r"(?:19|20)\d{2}\s*年(?:\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?)?")
CLAUSE_RE = re.compile(r"^(第[一二三四五六七八九十百千万0-9]+[章节条款])")
HEADING_RE = re.compile(
    r"^(?:#{1,6}\s+|"
    r"第[一二三四五六七八九十百千万0-9]+[章节]|"
    r"[一二三四五六七八九十百]+[、．.]|"
    r"[（(][一二三四五六七八九十0-9]+[)）]|"
    r"\d{1,2}(?:\.\d{1,2}){0,4}\s+)"
)
TABLE_HINT_RE = re.compile(r"\||\t| {2,}")


@dataclass(frozen=True)
class ChunkingConfig:
    target_chars: int = 512
    max_chars: int = 1024
    min_chars: int = 80
    overlap_chars: int = 80


def chunk_document(document: Document, pages: list[PageText], config: ChunkingConfig | None = None) -> list[Chunk]:
    """Chunk a document across all pages with shared section context and overlap."""
    config = config or ChunkingConfig()
    if not pages:
        return []

    output: list[Chunk] = []
    buffer: list[str] = []
    buffer_chars = 0
    active_section = ""
    active_clause = ""
    active_page = pages[0].page

    def flush() -> None:
        nonlocal buffer, buffer_chars
        body = _normalize("".join(buffer))
        if not body:
            buffer = []
            buffer_chars = 0
            return

        parts = _split_long_text(body, config.max_chars)
        for part in parts:
            if len(part) < config.min_chars and not _high_signal_short(part):
                continue
            output.append(
                _make_chunk(document, active_page, active_section, active_clause, part, len(output))
            )

        if config.overlap_chars > 0 and body:
            overlap = body[-config.overlap_chars :]
            buffer = [overlap]
            buffer_chars = len(overlap)
        else:
            buffer = []
            buffer_chars = 0

    for page in pages:
        for unit_text, section, clause, boundary in _logical_units(page.text):
            if boundary:
                flush()
                active_section = section or active_section
                active_clause = clause or active_clause
                active_page = page.page
            unit_len = len(unit_text)
            if buffer and buffer_chars + unit_len > config.max_chars:
                flush()
            buffer.append(unit_text)
            buffer_chars += unit_len
            if buffer_chars >= config.target_chars:
                flush()
    flush()
    return output


def extract_numbers(text: str) -> list[str]:
    return list(dict.fromkeys(match.group(0).strip() for match in NUMBER_RE.finditer(text or "") if match.group(0).strip()))


def extract_dates(text: str) -> list[str]:
    return list(dict.fromkeys(match.group(0).strip() for match in DATE_RE.finditer(text or "") if match.group(0).strip()))


def _logical_units(text: str) -> list[tuple[str, str, str, bool]]:
    units: list[tuple[str, str, str, bool]] = []
    section = ""
    clause = ""
    pending = ""

    def flush_pending() -> None:
        nonlocal pending
        for sentence in _split_sentences(pending):
            units.append((sentence, section, clause, False))
        pending = ""

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or _noise_line(line):
            continue
        clause_match = CLAUSE_RE.match(line)
        markdown_heading = re.match(r"^(#{1,6})\s+(.+)", line)
        is_heading = bool(HEADING_RE.match(line)) and len(line) <= 120
        if markdown_heading:
            flush_pending()
            section = markdown_heading.group(2).strip()
            units.append((line + "\n", section, clause, True))
            continue
        if clause_match or is_heading:
            flush_pending()
            if is_heading:
                section = line
            if clause_match:
                clause = clause_match.group(1)
            units.append((line + "\n", section, clause, True))
            continue
        if _looks_like_table_row(line):
            flush_pending()
            units.append((line + "\n", section or "table", clause, True))
            continue
        pending += line
        if line.endswith(("。", "；", ";", "！", "？")):
            flush_pending()
    flush_pending()
    return units


def _split_sentences(text: str) -> list[str]:
    text = _normalize(text)
    if not text:
        return []
    return [part for part in re.split(r"(?<=[。！？；;])", text) if part]


def _split_long_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    output: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            split = max(text.rfind(mark, start + max_chars // 2, end) for mark in ("。", "；", ";", "\n"))
            if split > start:
                end = split + 1
        output.append(text[start:end])
        start = end
    return output


def _make_chunk(document: Document, page: int, section: str, clause: str, text: str, index: int) -> Chunk:
    digest = hashlib.sha1(f"{document.doc_id}:{page}:{index}:{text}".encode()).hexdigest()[:12]
    numbers = extract_numbers(text)
    dates = extract_dates(text)
    chunk_type = "table_row" if _looks_like_table_row(text) else "atomic_text"
    context_prefix = " > ".join(part for part in (section, clause) if part)
    display_text = f"[{context_prefix}]\n{text}" if context_prefix else text
    return Chunk(
        chunk_id=f"{document.doc_id}:p{page}:c{index}:{digest}",
        doc_id=document.doc_id,
        domain=document.domain,
        page=page,
        section=section,
        clause_id=clause,
        text=display_text,
        numbers=numbers,
        dates=dates,
        tables=[text] if chunk_type == "table_row" else [],
        metadata={
            "title": document.title,
            "path": document.path,
            "chunk_type": chunk_type,
            "context_prefix": context_prefix,
            "extra_index_fields": _extra_index_fields(section, clause, numbers, dates),
        },
    )


def _extra_index_fields(section: str, clause: str, numbers: list[str], dates: list[str]) -> list[str]:
    return [field for field in [section, clause, *numbers, *dates] if field]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _noise_line(line: str) -> bool:
    compact = "".join(line.split())
    return compact in {"目录", "目次"} or bool(re.fullmatch(r"(?:第)?\d{1,4}(?:页)?", compact))


def _looks_like_table_row(line: str) -> bool:
    compact = str(line or "").strip()
    if len(compact) < 8:
        return False
    return bool(TABLE_HINT_RE.search(compact) and len(extract_numbers(compact)) >= 2)


def _high_signal_short(text: str) -> bool:
    return bool(extract_numbers(text) or CLAUSE_RE.match(text) or len(text) >= 40)
