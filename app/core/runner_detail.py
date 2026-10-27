"""
KangPaket — Pure helpers for Runner result detail (no GUI imports).

Capturing a request/response snapshot per result and turning it into display text.
"""
from __future__ import annotations

import json
import urllib.parse

from app.models.request_model import RequestProfile

# Max bytes of request body / response body kept per result (UTF-8). Rows beyond the
# render limit are still kept for Export, so this bounds memory: 2 * 200 KB per result.
MAX_DETAIL_BYTES = 200 * 1024

# Pretty-printing is skipped above this size (it is cheap, but keeps expand snappy).
_PRETTY_MAX_CHARS = 100_000

_BINARY_PREFIXES = ("image/", "audio/", "video/", "font/")
_BINARY_TYPES = (
    "application/octet-stream", "application/pdf", "application/zip",
    "application/gzip", "application/x-tar", "application/vnd.",
    "application/x-protobuf", "application/wasm",
)


def truncate_text(text: str | None, limit: int = MAX_DETAIL_BYTES) -> str | None:
    """Cut text to at most `limit` UTF-8 bytes, appending a marker with the total size."""
    if text is None:
        return None
    if len(text) * 4 <= limit:          # cannot exceed the limit; skip encoding
        return text
    raw = text.encode("utf-8", errors="replace")
    if len(raw) <= limit:
        return text
    cut = raw[:limit].decode("utf-8", errors="ignore")
    return f"{cut}\n… truncated ({len(raw)} bytes total)"


def describe_request_body(profile: RequestProfile) -> str | None:
    """Resolved body text that was sent, or None when the request has no body."""
    bt = profile.body_type
    if bt == "raw":
        return profile.body_content if profile.body_content != "" else None
    if bt in ("x-www-form-urlencoded", "form-data"):
        if not profile.body_form:
            return None
        if bt == "x-www-form-urlencoded":
            return urllib.parse.urlencode(profile.body_form)
        return "\n".join(f"{k}: {v}" for k, v in profile.body_form.items())
    return None


def _is_binary(content_type: str, body: str) -> bool:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct.startswith(_BINARY_PREFIXES) or ct.startswith(_BINARY_TYPES):
        return True
    return "\x00" in body[:2048]


def format_response_body(body: str | None, content_type: str, size_bytes: int | None) -> str:
    if body is None or body == "":
        return "(empty response)"
    if _is_binary(content_type, body):
        size = f"{size_bytes} bytes" if size_bytes is not None else "unknown size"
        return f"(binary content, {content_type or 'unknown content-type'}, {size})"
    if len(body) <= _PRETTY_MAX_CHARS:
        try:
            return json.dumps(json.loads(body), indent=2, ensure_ascii=False)
        except (ValueError, RecursionError):
            pass
    return body


def build_detail_sections(item) -> list[tuple[str, str]]:
    """(title, text) sections for the expanded result view."""
    url = item.request_url or "(not available)"
    method = item.method or ""
    req_line = f"{method} {url}".strip()
    payload = item.request_body if item.request_body else "(no body)"
    return [
        ("Request URL", req_line),
        ("Request payload", payload),
        ("Response body", format_response_body(
            item.response_body, item.response_content_type, item.size_bytes)
            if item.response_body is not None or item.status != "error"
            else "(no response)"),
    ]
