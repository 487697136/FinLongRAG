"""Chinese-friendly tokenization for sparse retrieval."""

from __future__ import annotations

import re
import sys
from pathlib import Path

STOP_WORDS = {
    "的",
    "了",
    "和",
    "与",
    "及",
    "或",
    "在",
    "是",
    "为",
    "对",
    "中",
    "根据",
    "下列",
    "以下",
    "关于",
    "哪些",
    "哪项",
    "正确",
    "错误",
}


def tokenize(text: str, mode: str = "mixed") -> list[str]:
    text = normalize_for_search(text)
    if not text:
        return []
    if mode == "char":
        return [char for char in text if not char.isspace()]
    if mode == "word":
        return _jieba_tokens(text)
    return _mixed_tokens(text)


def tokenize_chunk_text(text: str, fields: list[str] | None = None, mode: str = "mixed") -> list[str]:
    payload = " ".join([text, *(fields or [])])
    return tokenize(payload, mode=mode)


def normalize_for_search(text: str) -> str:
    return (
        str(text or "")
        .replace("％", "%")
        .replace("，", ",")
        .replace("\u3000", " ")
        .strip()
    )


def _jieba_tokens(text: str) -> list[str]:
    import jieba

    _configure_jieba_cache(jieba)
    return [token for token in jieba.lcut(text) if _keep_token(token)]


def _configure_jieba_cache(jieba_module) -> None:
    cache_dir = Path(sys.prefix) / "temp" / "jieba"
    cache_dir.mkdir(parents=True, exist_ok=True)
    jieba_module.dt.tmp_dir = str(cache_dir)


def _mixed_tokens(text: str) -> list[str]:
    tokens = _jieba_tokens(text)
    tokens.extend(re.findall(r"[A-Za-z0-9_.+-]+%?", text))
    compact = re.sub(r"\s+", "", text)
    tokens.extend(compact[index : index + 2] for index in range(max(0, len(compact) - 1)))
    return [token for token in tokens if _keep_token(token)]


def _keep_token(token: str) -> bool:
    token = token.strip()
    return bool(token and token not in STOP_WORDS and len(token) >= 1)
