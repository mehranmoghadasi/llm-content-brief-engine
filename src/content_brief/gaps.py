"""
gaps.py — Measure how many top-ranking pages actually cover a topic.

The LLM proposes candidate gap topics; this module replaces its guessed
``coverage_pct`` with a number computed from the crawled pages, so the brief
never reports a "gap" that half the SERP already covers.
"""

from __future__ import annotations

import re

from content_brief.parser import _STOP_WORDS as STOPWORDS
from content_brief.parser import ParsedPage

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9'-]+")


def significant_tokens(text: str, min_len: int = 3) -> list[str]:
    """Lower-cased content words of a topic string, stopwords removed."""
    return [t for t in _TOKEN_RE.findall(text.lower()) if len(t) >= min_len and t not in STOPWORDS]


def page_covers_topic(page: ParsedPage, topic: str, threshold: float = 0.6) -> bool:
    """A page covers a topic when at least ``threshold`` of the topic's content words
    appear in its visible text or headings. Short topics (1 word) need an exact hit."""
    tokens = significant_tokens(topic)
    if not tokens:
        return False
    haystack = page.text + " " + " ".join(h.text.lower() for h in page.headings)
    hits = sum(1 for t in tokens if t in haystack)
    return hits / len(tokens) >= threshold


def measure_coverage(topic: str, pages: list[ParsedPage]) -> int:
    """Percentage (0–100) of parsed pages that cover ``topic``."""
    if not pages:
        return 0
    covered = sum(1 for p in pages if page_covers_topic(p, topic))
    return round(100 * covered / len(pages))


def measure_gaps(gaps: list[dict], pages: list[ParsedPage], max_coverage: int = 50) -> list[dict]:
    """Attach measured coverage to each LLM-proposed gap and drop topics that most of the
    SERP already covers (they are not gaps). Sorted by coverage ascending = biggest gap first."""
    out = []
    for g in gaps:
        measured = measure_coverage(g["topic"], pages)
        if measured > max_coverage:
            continue
        out.append({**g, "coverage_pct": measured, "llm_estimate_pct": g.get("coverage_pct"), "measured": True})
    return sorted(out, key=lambda g: g["coverage_pct"])
