"""Apollo-native token-aware chunking for notebook sources.

Inspired by Open Notebook's content-aware chunking, but intentionally keeps
Apollo dependency-free apart from optional tiktoken.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

try:
    import tiktoken
except Exception:  # pragma: no cover - optional fallback
    tiktoken = None

DEFAULT_CHUNK_TOKENS = 400
DEFAULT_OVERLAP_TOKENS = 60

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_TAG_RE = re.compile(r"<([a-zA-Z][\w-]*)\b[^>]*>")
_WORD_RE = re.compile(r"\S+")


@dataclass(frozen=True)
class Chunk:
    text: str
    index: int
    content_type: str


_encoder = None


def _get_encoder():
    global _encoder
    if _encoder is None and tiktoken is not None:
        try:
            _encoder = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _encoder = False
    return _encoder if _encoder is not False else None


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def token_count(text: str) -> int:
    encoder = _get_encoder()
    if encoder is not None:
        try:
            return len(encoder.encode(text))
        except Exception:
            pass
    return len(_WORD_RE.findall(text))


def _tokens(text: str) -> list[str] | list[int]:
    encoder = _get_encoder()
    if encoder is not None:
        try:
            return encoder.encode(text)
        except Exception:
            pass
    return text.split()


def _decode_tokens(tokens: list[str] | list[int]) -> str:
    encoder = _get_encoder()
    if encoder is not None and tokens and isinstance(tokens[0], int):
        try:
            return encoder.decode(tokens)
        except Exception:
            pass
    return " ".join(str(token) for token in tokens)


def detect_content_type(filename: str, text: str = "") -> str:
    lower = filename.lower()
    if lower.endswith((".md", ".markdown")):
        return "markdown"
    if lower.endswith((".html", ".htm")):
        return "html"
    if re.search(r"<(?:html|body|article|section|p|h1|h2|h3)\b", text, re.IGNORECASE):
        return "html"
    if _HEADING_RE.search(text):
        return "markdown"
    return "plain"


def _structured_segments(text: str, content_type: str) -> list[str]:
    if content_type == "markdown":
        matches = list(_HEADING_RE.finditer(text))
        if not matches:
            return [text]
        segments: list[str] = []
        cursor = 0
        for match in matches:
            if match.start() > cursor:
                prefix = text[cursor:match.start()].strip()
                if prefix:
                    segments.append(prefix)
            cursor = match.start()
            # Keep a heading attached to the content that follows it.
        tail = text[cursor:].strip()
        if tail:
            segments.append(tail)
        return segments or [text]

    if content_type == "html":
        # Preserve visible text while keeping likely block boundaries.
        normalized = re.sub(r"</(?:p|div|section|article|li|h[1-6])>", "\n\n", text, flags=re.IGNORECASE)
        normalized = re.sub(r"<br\s*/?>", "\n", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"<[^>]+>", " ", normalized)
        normalized = clean_text(normalized)
        return [normalized] if normalized else []

    return [text]


def _split_segment(segment: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    segment = segment.strip()
    if not segment:
        return []
    tokens = _tokens(segment)
    if len(tokens) <= max_tokens:
        return [segment]

    results: list[str] = []
    step = max(1, max_tokens - overlap_tokens)
    for start in range(0, len(tokens), step):
        window = tokens[start:start + max_tokens]
        if not window:
            break
        results.append(_decode_tokens(window).strip())
        if start + max_tokens >= len(tokens):
            break
    return [item for item in results if item]


def chunk_text(
    text: str,
    filename: str = "source.txt",
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[Chunk]:
    """Return token-bounded chunks while preserving structured boundaries."""
    cleaned = clean_text(text)
    if not cleaned:
        return []
    max_tokens = max(32, int(chunk_tokens))
    overlap = max(0, min(int(overlap_tokens), max_tokens // 2))
    content_type = detect_content_type(filename, cleaned)
    segments = _structured_segments(cleaned, content_type)

    output: list[Chunk] = []
    for segment in segments:
        for piece in _split_segment(segment, max_tokens, overlap):
            output.append(Chunk(text=piece, index=len(output), content_type=content_type))
    return output
