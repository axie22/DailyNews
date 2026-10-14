from __future__ import annotations

import calendar
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

ARXIV_ID_RE = re.compile(r"(?:arxiv\.org/(?:abs|pdf)/|huggingface\.co/papers/)(\d{4}\.\d{4,5})")


def extract_arxiv_id(url: str) -> str | None:
    m = ARXIV_ID_RE.search(url or "")
    return m.group(1) if m else None


def strip_html(text: str, limit: int = 2000) -> str:
    if not text:
        return ""
    if "<" in text:
        text = BeautifulSoup(text, "lxml").get_text(" ")
    return re.sub(r"\s+", " ", text).strip()[:limit]


def struct_to_dt(st) -> datetime | None:
    if not st:
        return None
    return datetime.fromtimestamp(calendar.timegm(st), tz=timezone.utc)


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
