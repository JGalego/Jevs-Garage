"""Bounded, read-only retrieval helpers for public JSON data sources."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from jevs_garage.operations import SourceReceipt

MAX_SOURCE_BYTES = 8_000_000
USER_AGENT = "Jevs-Garage/0.1 (+https://github.com/JGalego/Jevs-Garage)"


class PublicDataError(RuntimeError):
    """Raised when a public source cannot produce a bounded JSON document."""


def fetch_json(
    *,
    name: str,
    url: str,
    source_updated_at: str = "reported in payload",
    timeout: float = 20,
) -> tuple[Any, SourceReceipt]:
    """Fetch one HTTPS JSON document and return it with an integrity receipt."""

    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise PublicDataError("public data URLs must use HTTPS")

    request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - URL is a source-code constant
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_SOURCE_BYTES:
                raise PublicDataError(f"{name} response exceeds {MAX_SOURCE_BYTES} bytes")
            payload = response.read(MAX_SOURCE_BYTES + 1)
    except (OSError, ValueError) as error:
        raise PublicDataError(f"Could not retrieve {name}: {error}") from error

    if len(payload) > MAX_SOURCE_BYTES:
        raise PublicDataError(f"{name} response exceeds {MAX_SOURCE_BYTES} bytes")
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PublicDataError(f"{name} did not return valid JSON: {error}") from error

    if isinstance(document, list):
        count = len(document)
    else:
        count = len(document.get("features", document.get("vulnerabilities", [])))
    receipt = SourceReceipt(
        name=name,
        url=url,
        fetched_at=datetime.now(UTC).isoformat(),
        source_updated_at=source_updated_at,
        record_count=count,
        content_sha256=hashlib.sha256(payload).hexdigest(),
    )
    return document, receipt
