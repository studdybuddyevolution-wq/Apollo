"""Phase 2 source ingestion for public web pages and YouTube transcripts."""

from __future__ import annotations

import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

import requests

from rag_service import add_source

MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024
REQUEST_TIMEOUT = 15
USER_AGENT = "Apollo Omni AI/Phase2"


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "canvas", "template"}:
            self._skip_depth += 1
        elif tag == "title" and self._skip_depth == 0:
            self._in_title = True

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "canvas", "template"} and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str):
        text = re.sub(r"\s+", " ", data).strip()
        if not text:
            return
        if self._in_title:
            self.title = (self.title + " " + text).strip()[:200]
        if self._skip_depth == 0:
            self.parts.append(text)


def _validate_public_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only public http:// or https:// URLs are supported")
    host = parsed.hostname.strip().lower()
    if host in {"localhost", "localhost.localdomain"}:
        raise ValueError("Localhost URLs are not allowed")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise ValueError("Could not resolve the URL host") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise ValueError("Private or local network URLs are not allowed")
    return parsed.geturl()


def _download(url: str) -> tuple[bytes, str]:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    response.raise_for_status()
    _validate_public_url(response.url)
    content = response.content
    if len(content) > MAX_DOWNLOAD_BYTES:
        raise ValueError("Source is larger than Apollo's 8 MB URL ingestion limit")
    return content, response.headers.get("content-type", "").lower()


def _html_to_text(raw: bytes) -> tuple[str, str]:
    parser = _TextExtractor()
    parser.feed(raw.decode("utf-8", errors="replace"))
    parser.close()
    text = "\n\n".join(parser.parts)
    if not text:
        raise ValueError("No readable text was found on the web page")
    return parser.title, text


def _slug_title(title: str, url: str, suffix: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._ -]+", " ", title).strip()
    if not base:
        base = urlparse(url).netloc or suffix
    return f"{base[:100]} [{suffix}]"


def extract_youtube_video_id(url: str) -> str:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if host in {"youtu.be", "www.youtu.be"}:
        candidate = parsed.path.strip("/").split("/")[0]
    elif host.endswith("youtube.com"):
        if parsed.path == "/watch":
            candidate = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith(("/shorts/", "/embed/", "/live/")):
            parts = parsed.path.strip("/").split("/")
            candidate = parts[1] if len(parts) > 1 else ""
        else:
            candidate = ""
    else:
        candidate = ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate or ""):
        raise ValueError("Invalid YouTube video URL")
    return candidate


def ingest_url(user_id: str | None, notebook_id: str, url: str) -> dict:
    safe_url = _validate_public_url(url)
    raw, content_type = _download(safe_url)
    if "application/pdf" in content_type or safe_url.lower().endswith(".pdf"):
        title = urlparse(safe_url).path.rstrip("/").split("/")[-1] or "web-document"
        filename = _slug_title(title.rsplit(".", 1)[0], safe_url, "URL") + ".pdf"
        return add_source(user_id, notebook_id, filename, raw)

    title, text = _html_to_text(raw)
    name = _slug_title(title, safe_url, "URL") + ".txt"
    payload = f"Source URL: {safe_url}\n\n{text}".encode("utf-8")
    return add_source(user_id, notebook_id, name, payload)


def ingest_youtube(user_id: str | None, notebook_id: str, url: str, languages: list[str] | None = None) -> dict:
    video_id = extract_youtube_video_id(url)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise RuntimeError("YouTube ingestion is not installed on this deployment") from exc

    transcript = YouTubeTranscriptApi().fetch(video_id, languages=languages or ["en"])
    lines = [snippet.text.strip() for snippet in transcript if getattr(snippet, "text", "").strip()]
    if not lines:
        raise ValueError("No transcript was available for this YouTube video")
    source_url = f"https://www.youtube.com/watch?v={video_id}"
    text = (
        f"YouTube URL: {source_url}\n"
        f"Transcript language: {getattr(transcript, 'language_code', 'unknown')}\n\n"
        + "\n\n".join(lines)
    )
    filename = f"YouTube {video_id}.txt"
    return add_source(user_id, notebook_id, filename, text.encode("utf-8"))
