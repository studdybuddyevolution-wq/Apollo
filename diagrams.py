"""
diagrams.py — Apollo Omni AI: Real, Rendered Diagrams (not just diagram *code*)

Two of Apollo's Studio tools ask the LLM for diagram markup (Mind Map asks
for Mermaid syntax) but historically just dumped that raw text in a code
block -- so students saw `graph TD; A-->B;` instead of an actual picture.
This module closes that loop for every kind of diagram a study app needs:

  * Structural diagrams (flowcharts, mind maps, timelines, sequence/
    architecture diagrams) -> the LLM writes Mermaid, we render it to a
    real colored SVG via the free public Kroki API (kroki.io -- no
    account, no key, just a POST of the diagram text).

  * Illustrative labeled diagrams (a cell, the heart, a plant, a circuit,
    a water cycle -- anything that needs real shapes and leader-line
    labels, not boxes-and-arrows) -> the LLM writes raw SVG directly
    (shapes + <text> labels + real fill colors), which we render as-is.

Both paths are $0 marginal cost beyond the Groq/Gemini call Apollo is
already making, and both give full control over color and labeling --
unlike text-to-image models, which hallucinate labels and get technical
shapes wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import requests

KROKI_URL = "https://kroki.io/mermaid/svg"
_REQUEST_TIMEOUT = 20

# Cyberpunk-orange theme matching the rest of Apollo's UI (charts.py uses
# the same #f97316 primary). Injected into Mermaid source automatically so
# the LLM doesn't have to remember a color palette every time.
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


# ---------------------------------------------------------------------------
# PARSING
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```(mermaid|svg)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
_BARE_SVG_RE = re.compile(r"(<svg[\s\S]*?</svg>)", re.IGNORECASE)


@dataclass
class ParsedDiagram:
  kind: str  # "mermaid" | "svg"
  code: str
  remaining_text: str


def parse_diagram_response(response_text: str) -> ParsedDiagram | None:
  """Pulls the fenced ```mermaid or ```svg block out of an LLM response.
  Falls back to a bare <svg>...</svg> match if the model forgot the fence.
  Returns None if nothing diagram-shaped was found."""
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


# ---------------------------------------------------------------------------
# SVG SANITIZATION (defensive -- strip anything executable before display)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# RENDERING
# ---------------------------------------------------------------------------

def _ensure_theme(mermaid_code: str) -> str:
  stripped = mermaid_code.strip()
  if stripped.startswith("%%{init"):
    return stripped
  return f"{_MERMAID_THEME_INIT}\n{stripped}"


def render_mermaid_to_svg(mermaid_code: str) -> tuple[bytes | None, str | None]:
  """POSTs Mermaid source to the free public Kroki API and returns
  (svg_bytes, error). Kroki needs no auth/key -- it's an open, self-hostable
  rendering service that wraps mermaid-cli/graphviz/plantuml/etc behind one
  HTTP endpoint."""
  themed = _ensure_theme(mermaid_code)
  try:
    resp = requests.post(
        KROKI_URL,
        data=themed.encode("utf-8"),
        headers={"Content-Type": "text/plain"},
        timeout=_REQUEST_TIMEOUT,
    )
    if resp.status_code == 200 and resp.content:
      return resp.content, None
    return None, f"Kroki returned {resp.status_code}: {resp.text[:200]}"
  except requests.RequestException as e:
    return None, f"Could not reach the diagram renderer (Kroki): {e}"


@dataclass
class RenderedDiagram:
  kind: str
  svg_bytes: bytes | None  # ready to hand to st.image()
  source_code: str  # original mermaid/svg text, for a "view source" expander / download
  error: str | None


def render_diagram(parsed: ParsedDiagram) -> RenderedDiagram:
  if parsed.kind == "svg":
    clean = sanitize_svg(parsed.code)
    return RenderedDiagram(kind="svg", svg_bytes=clean.encode("utf-8"), source_code=parsed.code, error=None)

  # mermaid
  svg_bytes, error = render_mermaid_to_svg(parsed.code)
  return RenderedDiagram(kind="mermaid", svg_bytes=svg_bytes, source_code=parsed.code, error=error)


def generate_and_render(topic_response_text: str) -> RenderedDiagram | None:
  """Convenience wrapper: parse an LLM response and render it in one call.
  Returns None if the response didn't contain a recognizable diagram block."""
  parsed = parse_diagram_response(topic_response_text)
  if parsed is None:
    return None
  return render_diagram(parsed)
