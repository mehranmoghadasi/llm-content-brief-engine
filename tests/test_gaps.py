"""Measured competitor coverage — the number the brief reports must come from the crawl."""

from content_brief.gaps import (
    measure_coverage,
    measure_gaps,
    page_covers_topic,
    significant_tokens,
)
from content_brief.parser import Heading, ParsedPage


def _page(url, text="", headings=()):
    return ParsedPage(url=url, meta_title=None, meta_description=None, word_count=len(text.split()),
                      headings=[Heading(2, h) for h in headings], text=text.lower())


def test_significant_tokens_drops_stopwords():
    assert significant_tokens("How to price a Calgary rental property") == ["price", "calgary", "rental", "property"]


def test_page_covers_topic_by_text_or_heading():
    p = _page("a", text="we compare rental yields across calgary neighbourhoods", headings=["Vacancy rates"])
    assert page_covers_topic(p, "Calgary rental yields")
    assert page_covers_topic(p, "vacancy rates")
    assert not page_covers_topic(p, "property tax appeals")


def test_measure_gaps_replaces_llm_guess_and_drops_non_gaps():
    pages = [
        _page("1", text="rent control rules and vacancy rates in alberta"),
        _page("2", text="vacancy rates explained"),
        _page("3", text="how to screen tenants"),
        _page("4", text="tenant screening checklist and vacancy rates"),
    ]
    gaps = [
        {"topic": "vacancy rates", "coverage_pct": 10, "opportunity": "x"},   # LLM says gap; really 75%
        {"topic": "rent control rules", "coverage_pct": 40, "opportunity": "y"},  # 25%
        {"topic": "insurance requirements", "coverage_pct": 0, "opportunity": "z"},  # 0%
    ]
    out = measure_gaps(gaps, pages)
    assert [g["topic"] for g in out] == ["insurance requirements", "rent control rules"]
    assert out[1]["coverage_pct"] == 25 and out[1]["llm_estimate_pct"] == 40 and out[1]["measured"]
    assert measure_coverage("vacancy rates", pages) == 75
    assert measure_coverage("anything", []) == 0
