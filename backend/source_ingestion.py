"""Phase 2 source ingestion for public web pages and YouTube transcripts."""

from __future__ import annotations

import functools
import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3 import PoolManager
from urllib3.util import connection as urllib3_connection

from rag_service import add_source, get_source_metadata

MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024
REQUEST_TIMEOUT = 15
MAX_REDIRECTS = 4
USER_AGENT = "Marklyf Omni AI/Phase2"


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


class _PinnedHTTPConnection(HTTPConnection):
    """HTTP connection that dials a validated IP but keeps the original host."""

    def __init__(self, host: str, port: int | None = None, *, pinned_ip: str, **kwargs):
        super().__init__(host=host, port=port, **kwargs)
        self._dns_host = pinned_ip

    @property
    def host(self) -> str:
        return self._pinned_host.rstrip(".")

    @host.setter
    def host(self, value: str) -> None:
        self._pinned_host = value


class _PinnedHTTPSConnection(HTTPSConnection):
    """HTTPS connection that dials a validated IP while preserving TLS SNI/hostname checks."""

    def __init__(self, host: str, port: int | None = None, *, pinned_ip: str, **kwargs):
        super().__init__(host=host, port=port, **kwargs)
        self._dns_host = pinned_ip

    @property
    def host(self) -> str:
        return self._pinned_host.rstrip(".")

    @host.setter
    def host(self, value: str) -> None:
        self._pinned_host = value


class _PinnedHTTPConnectionPool(HTTPConnectionPool):
    ConnectionCls = _PinnedHTTPConnection

    def __init__(self, *args, pinned_ip: str, **kwargs):
        self._pinned_ip = pinned_ip
        super().__init__(*args, **kwargs, pinned_ip=pinned_ip)


class _PinnedHTTPSConnectionPool(HTTPSConnectionPool):
    ConnectionCls = _PinnedHTTPSConnection

    def __init__(self, *args, pinned_ip: str, **kwargs):
        self._pinned_ip = pinned_ip
        super().__init__(*args, **kwargs, pinned_ip=pinned_ip)


class _PinnedIPAdapter(HTTPAdapter):
    """requests adapter whose pools connect to one validated IP address.

    The requested URL still contains the original hostname, so HTTP Host and
    HTTPS SNI/certificate verification remain bound to the validated hostname.
    """

    def __init__(self, pinned_ip: str, *args, **kwargs):
        self._pinned_ip = str(ipaddress.ip_address(pinned_ip))
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            **pool_kwargs,
        )
        self.poolmanager.pool_classes_by_scheme = {
            "http": functools.partial(_PinnedHTTPConnectionPool, pinned_ip=self._pinned_ip),
            "https": functools.partial(_PinnedHTTPSConnectionPool, pinned_ip=self._pinned_ip),
        }


def _validate_public_url(url: str) -> tuple[str, str]:
    """Return (validated_ip, original_url) for a public HTTP(S) URL."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only public http:// or https:// URLs are supported")
    host = parsed.hostname.strip().lower()
    if host in {"localhost", "localhost.localdomain"}:
        raise ValueError("Localhost URLs are not allowed")
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(
                host,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        }
    except OSError as exc:
        raise ValueError("Could not resolve the URL host") from exc
    if not addresses:
        raise ValueError("Could not resolve the URL host")

    safe_ip: str | None = None
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise ValueError("Private or local network URLs are not allowed")
        safe_ip = safe_ip or address

    if safe_ip is None:
        raise ValueError("Could not resolve the URL host")
    return safe_ip, parsed.geturl()


def _download(safe_ip: str, current: str) -> tuple[bytes, str]:
    with requests.Session() as session:
        # Proxies resolve the target on the proxy side, defeating the local IP pin.
        # Disable environment-provided proxies so every connection is pinned here.
        session.trust_env = False
        session.headers.update({"User-Agent": USER_AGENT})
        for _ in range(MAX_REDIRECTS + 1):
            adapter = _PinnedIPAdapter(safe_ip)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            response = session.get(current, timeout=REQUEST_TIMEOUT, allow_redirects=False, stream=True)
            if response.is_redirect:
                location = response.headers.get("Location")
                if not location:
                    response.close()
                    raise ValueError("URL redirect did not provide a destination")
                redirect_url = urljoin(current, location)
                response.close()
                safe_ip, current = _validate_public_url(redirect_url)
                continue
            response.raise_for_status()
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    response.close()
                    raise ValueError("Source is larger than Marklyf's 8 MB URL ingestion limit")
                chunks.append(chunk)
            return b"".join(chunks), response.headers.get("content-type", "").lower()
    raise ValueError("Too many URL redirects")


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
    safe_ip, safe_url = _validate_public_url(url)
    raw, content_type = _download(safe_ip, safe_url)
    if "application/pdf" in content_type or safe_url.lower().endswith(".pdf"):
        title = urlparse(safe_url).path.rstrip("/").split("/")[-1] or "web-document"
        filename = _slug_title(title.rsplit(".", 1)[0], safe_url, "URL") + ".pdf"
        return add_source(user_id, notebook_id, filename, raw, kind="url", source_url=safe_url)

    title, text = _html_to_text(raw)
    name = _slug_title(title, safe_url, "URL") + ".txt"
    payload = f"Source URL: {safe_url}\n\n{text}".encode("utf-8")
    return add_source(user_id, notebook_id, name, payload, kind="url", source_url=safe_url)


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
    return add_source(user_id, notebook_id, filename, text.encode("utf-8"), kind="youtube", source_url=source_url)

def refresh_url_source(user_id: str | None, notebook_id: str, source_name: str) -> dict:
    metadata = get_source_metadata(user_id, notebook_id, source_name)
    url = str((metadata or {}).get("source_url") or "").strip()
    if not url:
        raise ValueError("This source does not contain a refreshable web URL")

    safe_ip, safe_url = _validate_public_url(url)
    raw, content_type = _download(safe_ip, safe_url)
    is_pdf = "application/pdf" in content_type or safe_url.lower().endswith(".pdf")
    original_is_pdf = source_name.lower().endswith(".pdf")
    if is_pdf != original_is_pdf:
        raise ValueError("The refreshed URL changed content type. Delete and re-add the source so Marklyf can select the correct parser.")
    if is_pdf:
        payload = raw
    else:
        _, text = _html_to_text(raw)
        payload = f"Source URL: {safe_url}\n\n{text}".encode("utf-8")
    return add_source(user_id, notebook_id, source_name, payload, kind="url", source_url=safe_url)


def refresh_youtube_source(user_id: str | None, notebook_id: str, source_name: str) -> dict:
    metadata = get_source_metadata(user_id, notebook_id, source_name)
    url = str((metadata or {}).get("source_url") or "").strip()
    if not url:
        raise ValueError("This source does not contain a refreshable YouTube URL")
    video_id = extract_youtube_video_id(url)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise RuntimeError("YouTube ingestion is not installed on this deployment") from exc
    transcript = YouTubeTranscriptApi().fetch(video_id, languages=["en"])
    lines = [snippet.text.strip() for snippet in transcript if getattr(snippet, "text", "").strip()]
    if not lines:
        raise ValueError("No transcript was available for this YouTube video")
    language_code = getattr(transcript, "language_code", "unknown")
    text = (
        f"YouTube URL: {url}\n"
        f"Transcript language: {language_code}\n\n"
        + "\n\n".join(lines)
    )
    return add_source(user_id, notebook_id, source_name, text.encode("utf-8"), kind="youtube", source_url=url)
