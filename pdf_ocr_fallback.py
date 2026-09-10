"""
pdf_ocr_fallback.py — Apollo Omni AI: Rescue Garbled PDF Text

Some PDFs — very common with Sanskrit / Devanagari textbooks, question
papers, and scans typeset with legacy (pre-Unicode) fonts such as the old
"Sanskrit 2003", "Kruti Dev", "Shusha", "Xdvng" families — embed NO
ToUnicode CMap for the text they display. The glyphs render perfectly on
screen, but every text-extraction library (pypdf, PyMuPDF's get_text(),
pdfplumber, etc.) can only read the *raw character codes* the font uses
internally, which happen to be ordinary Latin letters/punctuation chosen
by whoever built the font — completely unrelated to the actual Devanagari
sound they represent. That produces exactly the kind of nonsense text
seen in Apollo's indexed-sources view ("Lokè;k;kH;lue~" instead of the
real word) even though nothing is technically "broken" about the PDF.

There is no way to recover the correct Unicode from the file itself —
the mapping was simply never stored. The only reliable fix is to stop
trusting the text layer and instead *look at the page*: rasterize it to
an image and read it the way a person would. This module does that by
reusing Apollo's existing Groq vision pipeline (vision_handler.py) as an
OCR engine, page by page, only for files where the text layer looks
untrustworthy (or is empty, e.g. a scanned image PDF).
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import pymupdf
from langchain_core.documents import Document as LangchainDocument

from vision_handler import ask_vision_model

# ---------------------------------------------------------------------------
# GARBLED-TEXT DETECTION
# ---------------------------------------------------------------------------

# Characters that show up constantly, mid-"word", in these legacy-font
# dumps but are rare inside real prose (English, IAST-transliterated
# Sanskrit, or proper Unicode Devanagari): things like ';', '~', '^',
# '%', backticks, pipes, stray slashes, etc. Real text uses these
# sparingly and almost always with whitespace nearby, not embedded
# inside what should be a single word.
_NOISE_CHARS = set(";~^%`|<>{}[]_\\/")

_STRIP_PUNCT = ".,()[]{}'\"!?:;—–"


def _strip_punct(token: str) -> str:
  return token.strip(_STRIP_PUNCT)


def _internal_upper_count(core: str) -> int:
  # Uppercase letters after the first character. A normal capitalized
  # word ("Vedas") or a standard camelCase identifier ("userId") has at
  # most one such letter; legacy-font glyph dumps routinely produce two
  # or more scattered capitals inside a single "word" because the font's
  # internal code table mixes upper/lower-case Latin slots more or less
  # arbitrarily to cover the full set of Devanagari glyphs.
  return sum(1 for ch in core[1:] if ch.isupper())


def _is_suspicious_token(token: str) -> bool:
  core = _strip_punct(token)
  if len(core) < 2:
    return False
  if any(ch in _NOISE_CHARS for ch in core):
    return True
  if not core.isupper() and any(ch.islower() for ch in core):
    if _internal_upper_count(core) >= 2:
      return True
  return False


def looks_garbled(text: str, sample_chars: int = 4000, token_threshold: float = 0.12, min_tokens: int = 12) -> bool:
  """Heuristic: does this extracted text look like a legacy non-Unicode
  font dump rather than real prose?

  Character-level "how much non-ASCII is in here" checks don't work,
  because this corruption is almost entirely printable ASCII/Latin-1 --
  and because it's common for only some *columns* of a page (e.g. the
  Devanagari word) to be corrupted while the surrounding English text
  extracts perfectly fine, diluting any whole-text character ratio.
  Instead we look token-by-token for the two things this corruption
  reliably produces: punctuation landing mid-word, and letters
  capitalized in the middle of a word -- both essentially never happen
  in real prose, in any language this app handles, but happen
  constantly when a font's internal glyph-to-codepoint table is being
  read back as if it were meaningful text.
  """
  if not text:
    return False
  sample = text[:sample_chars]
  tokens = sample.split()
  if len(tokens) < min_tokens:
    return False  # too little to judge reliably either way

  suspicious = sum(1 for t in tokens if _is_suspicious_token(t))
  return (suspicious / len(tokens)) > token_threshold


def combined_text(documents: list[LangchainDocument]) -> str:
  return "\n".join(d.page_content for d in documents if d.page_content)


# ---------------------------------------------------------------------------
# PAGE RASTERIZATION + VISION OCR
# ---------------------------------------------------------------------------

OCR_TRANSCRIBE_PROMPT = (
    "This is a page from a study document that may mix English, "
    "Sanskrit/Devanagari script, and IAST-style transliteration "
    "(diacritics like ā, ī, ū, ś, ṣ, ṇ, ṭ, ḍ, ṃ). Transcribe ALL text on "
    "this page exactly as it visually appears, left to right, top to "
    "bottom. Keep Devanagari script as actual Devanagari Unicode "
    "characters — do not transliterate or translate it. If the page has "
    "a table, reproduce each row on its own line with columns separated "
    "by ' | '. Output ONLY the transcribed text, with no preamble, no "
    "commentary, and no added explanation."
)


@dataclass
class OcrPageResult:
  page_number: int
  text: str
  ok: bool
  status: str


def render_pdf_pages_to_png(file_bytes: bytes, dpi: int = 220, max_pages: int = 60) -> list[bytes]:
  """Rasterizes each page of a PDF to PNG bytes using PyMuPDF (no system
  dependencies like poppler needed)."""
  images: list[bytes] = []
  doc = pymupdf.open(stream=file_bytes, filetype="pdf")
  try:
    zoom = dpi / 72.0
    matrix = pymupdf.Matrix(zoom, zoom)
    page_count = min(len(doc), max_pages)
    for i in range(page_count):
      page = doc.load_page(i)
      pix = page.get_pixmap(matrix=matrix)
      images.append(pix.tobytes("png"))
  finally:
    doc.close()
  return images


def ocr_pdf_via_vision(
    file_name: str,
    file_bytes: bytes,
    groq_key: str,
    max_pages: int = 60,
    dpi: int = 220,
) -> tuple[list[LangchainDocument], str | None]:
  """Renders each page as an image and transcribes it with the vision
  model, returning LangChain Documents in the same shape the rest of the
  app's indexing pipeline (text_splitter, FAISS, etc.) already expects.

  Returns (documents, warning). `warning` is set (but documents may still
  be non-empty) if some pages failed or the file was truncated at
  max_pages.
  """
  if not groq_key or not groq_key.startswith("gsk_"):
    return [], "OCR fallback needs a valid GROQ_API_KEY (starts with 'gsk_')."

  try:
    page_images = render_pdf_pages_to_png(file_bytes, dpi=dpi, max_pages=max_pages)
  except Exception as e:
    return [], f"Could not rasterize PDF pages for OCR: {e}"

  if not page_images:
    return [], "PDF appears to have no pages to OCR."

  total_pages_in_file = None
  try:
    with pymupdf.open(stream=file_bytes, filetype="pdf") as _d:
      total_pages_in_file = len(_d)
  except Exception:
    pass

  docs: list[LangchainDocument] = []
  failed_pages: list[int] = []

  for idx, png_bytes in enumerate(page_images, start=1):
    answer, status = ask_vision_model(
        png_bytes,
        "image/png",
        OCR_TRANSCRIBE_PROMPT,
        groq_key,
        max_tokens=2000,
        temperature=0.0,
    )
    if answer and answer.strip():
      docs.append(
          LangchainDocument(
              page_content=answer.strip(),
              metadata={
                  "source": file_name,
                  "page": idx - 1,
                  "ocr_fallback": True,
              },
          )
      )
    else:
      failed_pages.append(idx)

  warning_parts = []
  if failed_pages:
    warning_parts.append(f"{len(failed_pages)} page(s) failed OCR: {failed_pages}")
  if total_pages_in_file and total_pages_in_file > max_pages:
    warning_parts.append(
        f"only the first {max_pages} of {total_pages_in_file} pages were OCR'd"
    )

  warning = "; ".join(warning_parts) if warning_parts else None
  return docs, warning
