"""Scrapers for sites that publish no RSS feed (Anthropic, Goodfire).

A listing page is scanned for links of the form <host>/<section>/<slug>. Two layouts are
handled:
  • title/date inside the link            (anthropic.com/news)
  • an empty link next to an <h2> + date  (goodfire.com/blog) — read from the post's card

If the layout changes so that nothing matches, fetch() raises instead of silently
returning nothing, so the digest's source-health footer flags it.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from dailynews.sources.base import RawItem, Source
from dailynews.sources.util import strip_html

_DATE_RE = re.compile(r"\b([A-Z][a-z]{2,8})\.? (\d{1,2}),? (\d{4})\b")
_CATEGORIES = ("Announcements", "Product", "Policy", "Science", "Interpretability",
               "Alignment", "Societal Impacts", "Economic Research", "Case Study", "Research")
_HEADINGS = ["h1", "h2", "h3", "h4", "h5"]
_MAX_CARD_DEPTH = 5


def _parse_date(text: str) -> datetime | None:
    m = _DATE_RE.search(text or "")
    if not m:
        return None
    month, day, year = m.groups()
    for fmt, mon in (("%B %d %Y", month), ("%b %d %Y", month[:3])):   # "September" / "Sept" / "Sep"
        try:
            return datetime.strptime(f"{mon} {day} {year}", fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _title_from(node) -> str:
    heading = node.find(_HEADINGS)
    if heading:
        return strip_html(heading.get_text(" "), 300)
    text = _DATE_RE.sub("", strip_html(node.get_text(" "), 400))
    for c in _CATEGORIES:
        text = text.replace(c, "")
    return re.sub(r"\s+", " ", text).strip(" ·|-")


class ListingPageSource(Source):
    def __init__(self, key: str, url: str, group: str = "lab", lab: str | None = None,
                 min_interval_hours: float = 0.0):
        self.key, self.url, self.group, self.lab = key, url, group, lab
        self.min_interval_hours = min_interval_hours
        p = urlparse(url)
        self._base = f"{p.scheme}://{p.netloc}"
        section = "/" + p.path.strip("/").split("/")[0] + "/"            # "/news/", "/blog/"
        host = re.escape(p.netloc).replace(r"www\.", r"(?:www\.)?")
        self._pattern = re.compile(rf"^(?:https?://{host})?{re.escape(section)}[A-Za-z0-9][A-Za-z0-9_-]+/?$")

    def _norm(self, href: str) -> str | None:
        href = href.split("?")[0].split("#")[0]
        if not self._pattern.match(href):
            return None
        return urljoin(self._base, href).rstrip("/")

    def _card(self, a, url: str):
        """Nearest ancestor that holds this post's heading but no other post's link."""
        node = a
        for _ in range(_MAX_CARD_DEPTH):
            node = node.parent
            if node is None or node.name in ("body", "html"):
                return None
            links = {self._norm(x["href"]) for x in node.find_all("a", href=True)} - {None}
            if links - {url}:
                return None
            if node.find(_HEADINGS):
                return node
        return None

    async def fetch(self, client: httpx.AsyncClient) -> list[RawItem]:
        resp = await client.get(self.url, follow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        found: dict[str, RawItem] = {}
        for a in soup.find_all("a", href=True):
            url = self._norm(a["href"])
            if not url or url in found:
                continue
            node = a
            title = _title_from(a)
            if len(title) < 8:
                node = self._card(a, url)
                title = _title_from(node) if node is not None else ""
            if len(title) < 8:
                continue
            found[url] = RawItem(
                url=url, title=title, source=self.key, group=self.group, lab=self.lab,
                content="", published_at=_parse_date(node.get_text(" ")),
            )
        if not found:
            raise RuntimeError(f"no article links matched on {self.url} — page layout may have changed")
        return list(found.values())


# Backwards-compatible name used in sources.yaml loader.
AnthropicSource = ListingPageSource
