"""Apollo-native token-aware source chunking.

Inspired by Open Notebook's chunking patterns without adopting LangChain.
"""
from __future__ import annotations

import re
from typing import Any

try:
    import tiktoken
except Exception:  # pragma: no cover - optional fallback for constrained environments
    tiktoken = None

DEFAULT_CHUNK_TOKENS = 400
DEFAULT_OVERLAP_RATIO = 0.15

_MD_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
_HTML_HEADING_RE = re.compile(r"<h([1-6])[^>]*>(.*?)</h\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")
_WORD_RE = re.compile(r"\S+")


def _encoding():
    if tiktoken is None:
        return None
    try:
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


def token_count(text: str) -> int:
    enc = _encoding()
    if enc is not None:
        return len(enc.encode(text))
    return max(1, len(_WORD_RE.findall(text)))


def _truncate_tokens(text: str, max_tokens: int) -> str:
    enc = _encoding()
    if enc is None:
        return " ".join(_WORD_RE.findall(text)[:max_tokens])
    return enc.decode(enc.encode(text)[:max_tokens]).strip()


def detect_content_type(filename: str, text: str = "") -> str:
    lower = filename.lower()
    if lower.endswith((".html", ".htm")) or re.search(r"<h[1-6]\b|<p\b|<div\b", text, re.IGNORECASE):
        return "html"
    if lower.endswith((".md", ".markdown")) or re.search(r"^\s{0,3}#{1,6}\s+", text, re.MULTILINE):
        return "markdown"
    return "plain"


def _clean_text(text: str, content_type: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if content_type == "html":
        headings: list[str] = []
        for match in _HTML_HEADING_RE.finditer(text):
            heading = _TAG_RE.sub(" ", match.group(2)).strip()
            if heading:
                headings.append(heading)
        text = _TAG_RE.sub(" ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _structured_units(text: str, content_type: str) -> list[tuple[str, str | None]]:
    if content_type == "markdown":
        units: list[tuple[str, str | None]] = []
        current_heading: str | None = None
        buffer: list[str] = []
        for line in text.splitlines():
            match = _MD_HEADING_RE.match(line)
            if match:
                if buffer:
                    body = "\n".join(buffer).strip()
                    if body:
                        units.append((body, current_heading))
                    buffer = []
                current_heading = match.group(1).strip()
                continue
            buffer.append(line)
        if buffer:
            body = "\n".join(buffer).strip()
            if body:
                units.append((body, current_heading))
        return units

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return [(p, None) for p in paragraphs]


def _secondary_split(text: str, max_tokens: int) -> list[str]:
    if token_count(text) <= max_tokens:
        return [text.strip()]
    sentences = [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]
    if len(sentences) == 1:
        words = _WORD_RE.findall(text)
        out: list[str] = []
        current: list[str] = []
        for word in words:
            candidate = " ".join(current + [word])
            if current and token_count(candidate) > max_tokens:
                out.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            out.append(" ".join(current))
        return out

    out: list[str] = []
    current: list[str] = []
    for sentence in sentences:
        candidate = " ".join(current + [sentence])
        if current and token_count(candidate) > max_tokens:
            out.append(" ".join(current))
            current = [sentence]
        else:
            current.append(sentence)
    if current:
        out.append(" ".join(current))
    return out


def split_text(
    text: str,
    filename: str = "source.txt",
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
    overlap_ratio: float = DEFAULT_OVERLAP_RATIO,
) -> list[dict[str, Any]]:
    """Return token-bounded chunk records with source metadata."""
    content_type = detect_content_type(filename, text)
    cleaned = _clean_text(text, content_type)
    if not cleaned:
        return []

    units = _structured_units(cleaned, content_type)
    pieces: list[tuple[str, str | None]] = []
    for body, heading in units:
        for piece in _secondary_split(body, chunk_tokens):
            pieces.append((piece, heading))

    overlap_tokens = max(1, int(chunk_tokens * overlap_ratio))
    records: list[dict[str, Any]] = []
    current: list[tuple[str, str | None]] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current, current_tokens
        if not current:
            return
        heading = next((h for _, h in current if h), None)
        body = "\n\n".join((f"{heading}\n{part}" if heading else part) for part, _ in current).strip()
        if body:
            records.append(
                {
                    "chunk_index": len(records),
                    "content_type": content_type,
                    "text": body,
                }
            )
        if overlap_tokens > 0:
            retained: list[tuple[str, str | None]] = []
            retained_tokens = 0
            for item in reversed(current):
                item_tokens = token_count(item[0])
                if retained and retained_tokens + item_tokens > overlap_tokens:
                    break
                retained.append(item)
                retained_tokens += item_tokens
                if retained_tokens >= overlap_tokens:
                    break
            current = list(reversed(retained))
            current_tokens = retained_tokens
        else:
            current = []
            current_tokens = 0

    for piece, heading in pieces:
        piece_tokens = token_count(piece)
        if current and current_tokens + piece_tokens > chunk_tokens:
            flush()
        if piece_tokens > chunk_tokens:
            piece = _truncate_tokens(piece, chunk_tokens)
            piece_tokens = token_count(piece)
        current.append((piece, heading))
        current_tokens += piece_tokens
    flush()
    return records
