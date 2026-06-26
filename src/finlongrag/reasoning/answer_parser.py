"""Robust parsing for model outputs."""

from __future__ import annotations

import json
import re


def extract_json_object(text: str) -> dict | None:
    if not text:
        return None
    candidates: list[str] = []
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1))
    start = text.find("{")
    if start >= 0:
        depth = 0
        for index in range(start, len(text)):
            char = text[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start : index + 1])
                    break
    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def parse_answer(text: str, answer_format: str, valid_options: set[str] | None = None) -> str:
    valid_options = valid_options or {"A", "B", "C", "D"}
    obj = extract_json_object(text) or {}
    raw = str(obj.get("answer") or text or "").upper()
    letters = [letter for letter in re.findall(r"[A-Z]", raw) if letter in valid_options]
    if answer_format in {"mcq", "tf"}:
        return letters[0] if letters else ""
    if answer_format == "multi":
        return "".join(sorted(set(letters)))
    return str(obj.get("answer") or text or "").strip()

