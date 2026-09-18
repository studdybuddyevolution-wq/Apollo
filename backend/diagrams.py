"""
diagrams.py — Apollo Omni AI: Real, Rendered Diagrams (not just diagram *code*)

Two of Apollo's Studio tools ask the LLM for diagram markup (Mind Map asks
for Mermaid syntax) but historically just dumped that raw text in a code block.
This module renders structural diagrams through Kroki and sanitizes raw SVG.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

import requests

KROKI_URL = os.getenv("APOLLO_KROKI_URL", "https://kroki.io/mermaid/svg")
_REQUEST_TIMEOUT = float(os.getenv("KROKI_RENDER_TIMEOUT", "20"))

_MERMAID_THEME_INIT = (
    "%%{init: {'theme': 'base', 'themeVariables': { "
    "'primaryColor': '#f97316', 'primaryTextColor': '#0f0f11', "
    "'primaryBorderColor': '#ea580c', 'lineColor': '#38bdf8', "
    "'secondaryColor': '#4ade80', 'tertiaryColor': '#1a1a1d', "
    "'background': '#0f0f11', 'mainBkg': '#f97316', "
    "'nodeTextColor': '#0f0f11', 'textColor': '#e5e7eb', "
    "'edgeLabelBackground':'#1a1a1d' }}}%%"
)

DIAGRAM_GENERATION_INSTRUCTIONS = """You generate ONE diagram for a study app. Decide the right format for the topic, then output ONLY a single fenced code block -- no text before or after it.

DECISION RULE:
- If the topic is a process, workflow, hierarchy, timeline, comparison, decision tree, system architecture, or the relationship between named steps/components -> use MERMAID. Pick whichever Mermaid diagram type fits best (flowchart/graph, mindmap, sequenceDiagram, classDiagram, gantt, timeline, stateDiagram-v2). Use short, clear node labels (no truncation) and add `style` or `classDef` lines to color-code categories or stages meaningfully -- don't leave every node the same color if there are distinct groups. Output it as:
```mermaid
<diagram code>
```

- If the topic needs an actual illustrated object with parts to label (biology/anatomy, a cell, a plant, a circuit, a machine, a geographic/cyclical diagram like the water cycle) -> use raw SVG instead, since boxes-and-arrows can't draw a real shape. Requirements for the SVG:
  * `viewBox="0 0 800 600"` (or similar 4:3-ish canvas), `xmlns="http://www.w3.org/2000/svg"`.
  * Use real, distinct fill colors for different parts (hex colors), not just black outlines.
  * Every labeled part needs a `<text>` element with a readable font-size (16-20px) and, where the shape is small, a thin leader line (a `<line>` or `<path>`) connecting the label to the part it names.
  * Include a `<text>` title at the top of the canvas.
  * No `<script>` tags, no external references/images -- pure shapes, paths, and text only.
Output it as:
```svg
<svg ...>...</svg>
```

Do not explain your choice. Do not add a caption after the code block. Output nothing except the single fenced code block."""


def build_diagram_prompt(topic: str, context: str = "") -> str:
    ctx_block = f"\n\nUse ONLY this context if relevant:\n{context}" if context else ""
    return f"{DIAGRAM_GENERATION_INSTRUCTIONS}\n\nTOPIC: {topic}{ctx_block}"


_FENCE_RE = re.compile(r"```(mermaid|svg)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
_BARE_SVG_RE = re.compile(r"(<svg[\s\S]*?</svg>)", re.IGNORECASE)


@dataclass
class ParsedDiagram:
    kind: str
    code: str
    remaining_text: str


def parse_diagram_response(response_text: str) -> ParsedDiagram | None:
    if not response_text:
        return None
    match = _FENCE_RE.search(response_text)
    if match:
        kind = match.group(1).lower()
        code = match.group(2).strip()
        remaining = (response_text[:match.start()] + response_text[match.end():]).strip()
        return ParsedDiagram(kind=kind, code=code, remaining_text=remaining)
    bare = _BARE_SVG_RE.search(response_text)
    if bare:
        code = bare.group(1).strip()
        remaining = (response_text[:bare.start()] + response_text[bare.end():]).strip()
        return ParsedDiagram(kind="svg", code=code, remaining_text=remaining)
    return None


_SCRIPT_TAG_RE = re.compile(r"<script[\s\S]*?</script>", re.IGNORECASE)
_ON_EVENT_ATTR_RE = re.compile(r'\s+on\w+\s*=\s*"[^"]*"', re.IGNORECASE)
_JS_HREF_RE = re.compile(r'(href\s*=\s*")javascript:[^"]*"', re.IGNORECASE)


def sanitize_svg(svg_code: str) -> str:
    cleaned = _SCRIPT_TAG_RE.sub("", svg_code)
    cleaned = _ON_EVENT_ATTR_RE.sub("", cleaned)
    cleaned = _JS_HREF_RE.sub(r'\1#"', cleaned)
    if "xmlns=" not in cleaned.split(">", 1)[0]:
        cleaned = cleaned.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
    return cleaned


def _ensure_theme(mermaid_code: str) -> str:
    stripped = mermaid_code.strip()
    if stripped.startswith("%%{init"):
        return stripped
    return f"{_MERMAID_THEME_INIT}\n{stripped}"


def render_mermaid_to_svg(mermaid_code: str, timeout: float | None = None) -> tuple[bytes | None, str | None]:
    themed = _ensure_theme(mermaid_code)
    request_timeout = _REQUEST_TIMEOUT if timeout is None else max(0.1, float(timeout))
    try:
        resp = requests.post(
            KROKI_URL,
            data=themed.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
            timeout=request_timeout,
        )
        if resp.status_code == 200 and resp.content:
            return resp.content, None
        return None, f"Kroki returned {resp.status_code}: {resp.text[:200]}"
    except requests.RequestException as e:
        return None, f"Could not reach the diagram renderer (Kroki): {e}"


@dataclass
class RenderedDiagram:
    kind: str
    svg_bytes: bytes | None
    source_code: str
    error: str | None


def render_diagram(parsed: ParsedDiagram, render_timeout: float | None = None) -> RenderedDiagram:
    if parsed.kind == "svg":
        clean = sanitize_svg(parsed.code)
        return RenderedDiagram(kind="svg", svg_bytes=clean.encode("utf-8"), source_code=parsed.code, error=None)
    svg_bytes, error = render_mermaid_to_svg(parsed.code, timeout=render_timeout)
    return RenderedDiagram(kind="mermaid", svg_bytes=svg_bytes, source_code=parsed.code, error=error)


def generate_and_render(topic_response_text: str, render_timeout: float | None = None) -> RenderedDiagram | None:
    parsed = parse_diagram_response(topic_response_text)
    if parsed is None:
        return None
    return render_diagram(parsed, render_timeout=render_timeout)


_STOPWORDS = {"the","a","an","and","or","of","to","in","on","for","with","is","are","was","were","this","that","it","as","by","at","from"}
_MERMAID_SYNTAX_RE = re.compile(r"%%.*|^\s*(graph|flowchart|mindmap|sequenceDiagram|classDiagram|gantt|timeline|stateDiagram-v2|participant|classDef|style|direction)\b.*$", re.IGNORECASE | re.MULTILINE)
_MERMAID_ARROW_RE = re.compile(r"-->|--\>|==>|-\.->|--x|--o|\|.*?\|")
_SVG_TEXT_RE = re.compile(r"<text[^>]*>(.*?)</text>", re.IGNORECASE | re.DOTALL)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")
_WORD_RE = re.compile(r"[A-Za-z]{3,}")


def _extract_label_words(kind: str, code: str) -> set[str]:
    if kind == "svg":
        texts = _SVG_TEXT_RE.findall(code)
        blob = " ".join(_TAG_STRIP_RE.sub(" ", t) for t in texts)
    elif kind == "text":
        blob = code
    else:
        blob = _MERMAID_SYNTAX_RE.sub(" ", code)
        blob = _MERMAID_ARROW_RE.sub(" ", blob)
        blob = re.sub(r"[\[\]{}()\"']", " ", blob)
    return {w.lower() for w in _WORD_RE.findall(blob) if w.lower() not in _STOPWORDS}


def content_overlap_ratio(kind: str, code: str, student_content: str) -> float:
    label_words = _extract_label_words(kind, code)
    if not label_words:
        return 1.0
    source_words = {w.lower() for w in _WORD_RE.findall(student_content)}
    matched = sum(1 for w in label_words if w in source_words)
    return matched / len(label_words)
