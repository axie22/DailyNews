"""Anthropic publishes no RSS feed, so the /news and /research listing pages are scraped.

This is the most fragile source: if the page layout changes, fetch() raises (instead of
silently returning nothing) so the digest's source-health footer flags it.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from dailynews.sources.base import RawItem, Source
from dailynews.sources.util import strip_html

_DATE_RE = re.compile(r"\b([A-Z][a-z]{2,8}) (\d{1,2}), (\d{4})\b")
_CATEGORIES = ("Announcements", "Product", "Policy", "Science", "Interpretability",
               "Alignment", "Societal Impacts", "Economic Research", "Case Study", "Research")


def _parse_date(text: str) -> datetime | None:
    m = _DATE_RE.search(text)
    if not m:
        return None
    for fmt in ("%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _clean_title(anchor) -> str:
    heading = anchor.find(["h1", "h2", "h3", "h4", "h5"])
    if heading:
        return strip_html(heading.get_text(" "), 300)
    text = strip_html(anchor.get_text(" "), 400)
    text = _DATE_RE.sub("", text)
    for c in _CATEGORIES:
        text = text.replace(c, "")
    return re.sub(r"\s+", " ", text).strip(" ·|-")


class AnthropicSource(Source):
    def __init__(self, key: str, url: str, group: str = "lab", lab: str = "anthropic",
                 min_interval_hours: float = 0.0):
        self.key, self.url, self.group, self.lab = key, url, group, lab
        self.min_interval_hours = min_interval_hours
        self._path = "/" + url.rstrip("/").rsplit("/", 1)[-1] + "/"   # "/news/" or "/research/"

    async def fetch(self, client: httpx.AsyncClient) -> list[RawItem]:
        resp = await client.get(self.url, follow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        seen, items = set(), []
        pattern = re.compile(r"^(?:https://www\.anthropic\.com)?" + re.escape(self._path) + r"[a-z0-9][a-z0-9-]+/?$")
        for a in soup.find_all("a", href=True):
            href = a["href"].split("?")[0].split("#")[0]
            if not pattern.match(href):
                continue
            url = urljoin("https://www.anthropic.com", href).rstrip("/")
            if url in seen:
                continue
            title = _clean_title(a)
            if len(title) < 8:
                continue
            seen.add(url)
            items.append(RawItem(
                url=url, title=title, source=self.key, group=self.group, lab=self.lab,
                content="", published_at=_parse_date(a.get_text(" ")),
            ))
        if not items:
            raise RuntimeError(f"no article links matched on {self.url} — page layout may have changed")
        return items
