"""
parser.py — Extract structured signals from crawled HTML pages.

For each page this module extracts:
- Heading hierarchy (H1/H2/H3) with text content
- Approximate word count (visible text)
- Meta title and description
- Named entity candidates (noun-phrase frequency analysis)
- People Also Ask questions (from SERP HTML, if present)
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from bs4 import BeautifulSoup, NavigableString, Tag

# Tags whose text content to exclude from word count / entity extraction
_IGNORED_TAGS = {
    "script", "style", "head", "nav", "footer", "header",
    "aside", "noscript", "figure", "figcaption",
}

# Minimum character length for a heading to be included
_MIN_HEADING_LEN = 4

# Stop words to exclude from entity frequency analysis
_STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "are", "was", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "can", "this", "that",
    "these", "those", "it", "its", "they", "them", "their", "what", "which",
    "who", "how", "when", "where", "why", "all", "any", "both", "each",
    "few", "more", "most", "other", "some", "such", "than", "then", "so",
    "up", "out", "if", "no", "not", "only", "same", "own", "also", "just",
    "about", "into", "through", "after", "over", "between", "your", "our",
    "their", "my", "we", "you", "he", "she", "i", "us", "me", "him", "her",
}


@dataclass
class Heading:
    level: int          # 1, 2, or 3
    text: str


@dataclass
class ParsedPage:
    """Structured signals extracted from a single crawled page."""

    url: str
    meta_title: Optional[str]
    meta_description: Optional[str]
    word_count: int
    headings: list[Heading] = field(default_factory=list)
    top_entities: list[tuple[str, int]] = field(default_factory=list)  # (entity, freq)
    paa_questions: list[str] = field(default_factory=list)  # if SERP page


def _get_visible_text(soup: BeautifulSoup) -> str:
    """Return all visible text content, stripping ignored tag content."""
    texts: list[str] = []
    for element in soup.descendants:
        if isinstance(element, NavigableString):
            parent = element.parent
            if parent and getattr(parent, "name", None) not in _IGNORED_TAGS:
                text = str(element).strip()
                if text:
                    texts.append(text)
    return " ".join(texts)


def _extract_headings(soup: BeautifulSoup) -> list[Heading]:
    """Extract H1, H2, H3 in document order."""
    headings: list[Heading] = []
    for tag in soup.find_all(["h1", "h2", "h3"]):
        text = tag.get_text(separator=" ", strip=True)
        level = int(tag.name[1])
        if len(text) >= _MIN_HEADING_LEN:
            headings.append(Heading(level=level, text=text))
    return headings


def _extract_meta(soup: BeautifulSoup) -> tuple[Optional[str], Optional[str]]:
    """Return (meta_title, meta_description)."""
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None

    desc_tag = soup.find("meta", attrs={"name": "description"})
    if not desc_tag:
        desc_tag = soup.find("meta", attrs={"property": "og:description"})
    description = desc_tag.get("content", "").strip() if desc_tag else None

    return title, description


def _extract_entities(text: str, top_n: int = 20) -> list[tuple[str, int]]:
    """
    Lightweight noun-phrase extraction using 2/3-gram frequency.

    We tokenize the visible text into lowercase words, generate 2- and 3-grams,
    filter stop words, and return the most frequent candidates. This is intentionally
    fast (no NLP model dependency) — the LLM phase does deeper entity understanding.
    """
    words = re.findall(r"[a-z][a-z\-']{2,}", text.lower())
    words = [w for w in words if w not in _STOP_WORDS and len(w) > 3]

    candidates: list[str] = []
    # Bigrams
    for i in range(len(words) - 1):
        candidates.append(f"{words[i]} {words[i + 1]}")
    # Trigrams
    for i in range(len(words) - 2):
        candidates.append(f"{words[i]} {words[i + 1]} {words[i + 2]}")
    # Single meaningful words
    candidates.extend(words)

    counter = Counter(candidates)
    return counter.most_common(top_n)


def _extract_paa_questions(soup: BeautifulSoup) -> list[str]:
    """
    Extract People Also Ask questions from a SERP page (DuckDuckGo or Google HTML).
    Falls back to FAQ schema if present on a regular page.
    """
    questions: list[str] = []

    # DuckDuckGo related searches (used as PAA proxy)
    for tag in soup.select(".related-searches a, .result__extras a"):
        text = tag.get_text(strip=True)
        if text and text not in questions:
            questions.append(text)

    # FAQ-schema style questions (works on regular pages too)
    for faq_item in soup.select("[itemtype*='FAQPage'] [itemprop='name']"):
        text = faq_item.get_text(strip=True)
        if text and "?" in text and text not in questions:
            questions.append(text)

    # Question-like headings on page (H2/H3 containing ?)
    for tag in soup.find_all(["h2", "h3"]):
        text = tag.get_text(separator=" ", strip=True)
        if "?" in text and text not in questions:
            questions.append(text)

    return questions[:15]


def parse_page(url: str, html: str) -> ParsedPage:
    """
    Parse a single page's HTML into structured signals.

    Args:
        url: The URL of the page (used as identifier).
        html: Raw HTML content of the page.

    Returns:
        ParsedPage with headings, word count, meta, entities, PAA questions.
    """
    soup = BeautifulSoup(html, "lxml")

    meta_title, meta_description = _extract_meta(soup)
    headings = _extract_headings(soup)
    visible_text = _get_visible_text(soup)
    word_count = len(visible_text.split())
    entities = _extract_entities(visible_text)
    paa = _extract_paa_questions(soup)

    return ParsedPage(
        url=url,
        meta_title=meta_title,
        meta_description=meta_description,
        word_count=word_count,
        headings=headings,
        top_entities=entities,
        paa_questions=paa,
    )


def parse_all_pages(pages: list) -> list[ParsedPage]:
    """Parse a list of PageResult objects into ParsedPage objects."""
    parsed: list[ParsedPage] = []
    for page in pages:
        if page.error or not page.html:
            continue
        try:
            parsed.append(parse_page(page.url, page.html))
        except Exception:
            # Parsing errors on individual pages are non-fatal
            continue
    return parsed
