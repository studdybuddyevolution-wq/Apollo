"""Selective vision fallback for scanned or legacy-font PDFs.

Adapted from Apollo's existing Streamlit vision pipeline and the selective
page-rendering idea used by OpenStudy. Only pages with empty or garbled text
are rendered, which avoids sending normal text PDFs through a vision model.
"""

from __future__ import annotations

import base64
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import pymupdf
from groq import Groq

VISION_MODELS = [
    os.getenv("APOLLO_VISION_MODEL", "qwen/qwen3.6-27b"),
    "qwen/qwen3.8-27b",
]
OCR_PROMPT = (
    "Transcribe this document page exactly as it appears. Preserve tables by "
    "using the pipe character between columns. Preserve formulas, headings, "
    "numbers and Devanagari or other non-Latin scripts as Unicode. Do not "
    "summarize, translate or add commentary. Return only the page text."
)

_NOISE = set(";~^%|<>{}[]_\\/")


def _is_garbled(text: str) -> bool:
    words = text.split()
    if len(words) < 10:
        return False
    suspicious = 0
    sample = words[:250]
    for word in sample:
        core = word.strip(".,()[]{}'\"!?:;—–")
        if len(core) < 2:
            continue
        if any(ch in _NOISE for ch in core):
            suspicious += 1
            continue
        internal_caps = sum(1 for ch in core[1:] if ch.isupper())
        if internal_caps >= 2 and not core.isupper():
            suspicious += 1
    return suspicious / max(len(sample), 1) > 0.12


def _page_needs_vision(text: str) -> bool:
    cleaned = " ".join((text or "").split())
    if len(cleaned) < 80:
        return True
    return _is_garbled(cleaned)


def _render_page(page: pymupdf.Page, dpi: int = 160) -> bytes:
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    return pix.tobytes("png")


def _vision_page(image: bytes, api_key: str, max_tokens: int = 2200) -> str:
    data_url = "data:image/png;base64," + base64.b64encode(image).decode("ascii")
    last_error: Exception | None = None
    for model in dict.fromkeys(VISION_MODELS):
        try:
            client = Groq(api_key=api_key)
            completion = client.chat.completions.create(
                model=model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": OCR_PROMPT},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }],
                temperature=0.0,
                max_tokens=max_tokens,
            )
            text = str(completion.choices[0].message.content or "").strip()
            if text:
                return text
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Vision OCR failed: {last_error}")


def extract_pdf_text_with_vision(
    raw: bytes,
    *,
    max_pages: int | None = None,
    concurrency: int | None = None,
) -> tuple[str, dict]:
    """Extract PDF text, selectively replacing unreadable pages with vision OCR."""
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    max_pages = max_pages or int(os.getenv("APOLLO_PDF_VISION_MAX_PAGES", "40"))
    concurrency = concurrency or int(os.getenv("APOLLO_PDF_VISION_CONCURRENCY", "3"))

    doc = pymupdf.open(stream=raw, filetype="pdf")
    try:
        page_texts = [page.get_text("text") or "" for page in doc]
        suspect = [index for index, text in enumerate(page_texts) if _page_needs_vision(text)]
        if not suspect or not api_key or not api_key.startswith("gsk_"):
            return "\n\n".join(
                f"[Page {i + 1}]\n{text.strip()}" for i, text in enumerate(page_texts) if text.strip()
            ), {
                "vision_used": False,
                "vision_pages": [],
                "vision_skipped_pages": suspect,
                "warning": "Vision fallback unavailable." if suspect and not api_key else None,
            }

        selected = suspect[:max_pages]
        outputs: dict[int, str] = {}
        failures: list[int] = []
        with ThreadPoolExecutor(max_workers=max(1, min(concurrency, 6))) as pool:
            futures = {
                pool.submit(_vision_page, _render_page(doc[index]), api_key): index
                for index in selected
            }
            for future in as_completed(futures):
                index = futures[future]
                try:
                    outputs[index] = future.result()
                except Exception:
                    failures.append(index)

        merged: list[str] = []
        for index, original in enumerate(page_texts):
            text = outputs.get(index, original)
            if text.strip():
                merged.append(f"[Page {index + 1}]\n{text.strip()}")

        skipped = suspect[max_pages:]
        warning_parts = []
        if failures:
            warning_parts.append(f"{len(failures)} page(s) failed vision OCR")
        if skipped:
            warning_parts.append(f"{len(skipped)} unreadable page(s) exceeded the vision page cap")
        return "\n\n".join(merged), {
            "vision_used": bool(outputs),
            "vision_pages": sorted(index + 1 for index in outputs),
            "vision_skipped_pages": [index + 1 for index in skipped],
            "warning": "; ".join(warning_parts) or None,
        }
    finally:
        doc.close()
