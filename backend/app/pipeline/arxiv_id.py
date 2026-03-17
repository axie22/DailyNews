import re

ARXIV_PATTERN = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})")


def extract_arxiv_id(url: str) -> str | None:
    m = ARXIV_PATTERN.search(url)
    return m.group(1) if m else None
