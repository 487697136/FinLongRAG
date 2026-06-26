"""Structure-aware chunking for financial long documents."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from finlongrag.core.schema import Chunk, Document, PageText

NUMBER_RE = re.compile(r"[-+]?(?:\d{1,3}(?:[,，]\d{3})+|\d+)(?:\.\d+)?\s*(?:%|％|元|万元|亿元|万|亿|倍|天|日|月|年)?")
DATE_RE = re.compile(r"(?:19|20)\d{2}\s*年(?:\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?)?")
CLAUSE_RE = re.compile(r"^(第[一二三四五六七八九十百千万0-9]+[章节条款])")
HEADING_RE = re.compile(
    r"^(?:第[一二三四五六七八九十百千万0-9]+[章节]|"
    r"[一二三四五六七八九十百]+[、．.]|"
    r"[（(][一二三四五六七八九十0-9]+[)）]|"
    r"\d{1,2}(?:\.\d{1,2}){0,4}\s+)"
)
TABLE_HINT_RE = re.compile(r"\||\t| {2,}")


@dataclass(frozen=True)
class ChunkingConfig:
    target_chars: int = 420
    max_chars: int = 720
    min_chars: int = 48


def chunk_document(document: Document, pages: list[PageText], config: ChunkingConfig | None = None) -> list[Chunk]:
    config = config or ChunkingConfig()
    output: list[Chunk] = []
    for page in pages:
        output.extend(_chunk_page(document, page, config, start_index=len(output)))
    return output


def extract_numbers(text: str) -> list[str]:
    return list(dict.fromkeys(match.group(0).strip() for match in NUMBER_RE.finditer(text or "") if match.group(0).strip()))


def extract_dates(text: str) -> list[str]:
    return list(dict.fromkeys(match.group(0).strip() for match in DATE_RE.finditer(text or "") if match.group(0).strip()))


def _chunk_page(document: Document, page: PageText, config: ChunkingConfig, start_index: int) -> list[Chunk]:
    units = _logical_units(page.text)
    output: list[Chunk] = []
    buffer: list[str] = []
    active_section = ""
    active_clause = ""

    def flush() -> None:
        nonlocal buffer
        body = _normalize("".join(buffer))
        buffer = []
        if not body:
            return
        for part in _split_long_text(body, config.max_chars):
            if len(part) < config.min_chars and not _high_signal_short(part):
                continue
            output.append(_make_chunk(document, page.page, active_section, active_clause, part, start_index + len(output)))

    for unit_text, section, clause, boundary in units:
        if boundary:
            flush()
            active_section = section or active_section
            active_clause = clause or active_clause
        candidate = _normalize("".join([*buffer, unit_text]))
        if buffer and len(candidate) > config.max_chars:
            flush()
        buffer.append(unit_text)
        if len(_normalize("".join(buffer))) >= config.target_chars:
            flush()
    flush()
    return output


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
        is_heading = bool(HEADING_RE.match(line)) and len(line) <= 120
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
    return Chunk(
        chunk_id=f"{document.doc_id}:p{page}:c{index}:{digest}",
        doc_id=document.doc_id,
        domain=document.domain,
        page=page,
        section=section,
        clause_id=clause,
        text=text,
        numbers=numbers,
        dates=dates,
        tables=[text] if chunk_type == "table_row" else [],
        metadata={
            "title": document.title,
            "path": document.path,
            "chunk_type": chunk_type,
            "extra_index_fields": _extra_index_fields(section, clause, numbers, dates, text),
        },
    )


def _extra_index_fields(section: str, clause: str, numbers: list[str], dates: list[str], text: str) -> list[str]:
    fields = [section, clause, *numbers, *dates]
    for term in ("营业收入", "净利润", "现金流", "研发投入", "分红", "保险金", "罚款", "期限", "票面利率"):
        if term in text:
            fields.append(term)
    return [field for field in fields if field]


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
    return bool(extract_numbers(text) or CLAUSE_RE.match(text) or any(term in text for term in ("应当", "不得", "保险金", "净利润")))

