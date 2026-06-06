"""Tests for the brief builder / model assembly module."""

from content_brief.brief_builder import (
    build_brief, _aggregate_entities, _aggregate_paa, _build_competitor_summaries
)
from content_brief.parser import ParsedPage, Heading
from content_brief.llm_analyzer import (
    BriefAnalysis, HeadingSuggestion, CompetitorGap
)


def _make_page(url: str, word_count: int = 1500, headings=None, paa=None):
    return ParsedPage(
        url=url,
        meta_title=f"Title for {url}",
        meta_description="Some description.",
        word_count=word_count,
        headings=headings or [
            Heading(level=1, text="Main Heading"),
            Heading(level=2, text="Section One"),
            Heading(level=2, text="Section Two"),
        ],
        top_entities=[("email marketing", 5), ("drip campaigns", 3), ("hubspot", 2)],
        paa_questions=paa or ["What is email marketing?", "How to automate email?"],
    )


def _make_analysis(keyword: str = "test keyword") -> BriefAnalysis:
    return BriefAnalysis(
        keyword=keyword,
        search_intent="Commercial investigation",
        word_count_min=1800,
        word_count_max=2400,
        tone="Authoritative and educational",
        heading_structure=[
            HeadingSuggestion(level=1, text="Test H1", notes=None),
            HeadingSuggestion(level=2, text="Test H2", notes="Some note"),
        ],
        entities_to_cover=["HubSpot", "email automation", "drip campaigns"],
        competitor_gaps=[
            CompetitorGap(
                topic="Self-hosted solutions",
                coverage_pct=10,
                opportunity="Most guides ignore self-hosted options",
            )
        ],
        intro_hook_suggestions=["Hook A", "Hook B", "Hook C"],
        paa_to_answer=["What is email marketing automation?"],
        estimated_internal_links=3,
        meta_title_suggestion="Best Email Automation for Agencies",
        meta_description_suggestion="Learn how to automate email marketing for your agency.",
    )


def test_build_brief_produces_correct_keyword():
    pages = [_make_page("https://a.com"), _make_page("https://b.com")]
    analysis = _make_analysis("email marketing automation")
    brief = build_brief("email marketing automation", pages, analysis)
    assert brief.keyword == "email marketing automation"


def test_build_brief_computes_avg_word_count():
    pages = [_make_page("https://a.com", 1000), _make_page("https://b.com", 2000)]
    analysis = _make_analysis()
    brief = build_brief("test", pages, analysis)
    assert brief.avg_competitor_word_count == 1500


def test_build_brief_includes_all_llm_fields():
    pages = [_make_page("https://a.com")]
    analysis = _make_analysis()
    brief = build_brief("test", pages, analysis)
    assert brief.search_intent == "Commercial investigation"
    assert brief.word_count_min == 1800
    assert brief.word_count_max == 2400
    assert len(brief.heading_structure) == 2
    assert len(brief.entities_to_cover) == 3


def test_aggregate_paa_deduplicates():
    pages = [
        _make_page("https://a.com", paa=["Question A?", "Question B?"]),
        _make_page("https://b.com", paa=["question a?", "Question C?"]),  # dupe (case-insensitive)
    ]
    result = _aggregate_paa(pages)
    # "Question A?" and "question a?" are duplicates — only one should appear
    q_lower = [q.lower() for q in result]
    assert q_lower.count("question a?") == 1


def test_build_competitor_summaries_length():
    pages = [_make_page(f"https://example{i}.com") for i in range(5)]
    summaries = _build_competitor_summaries(pages)
    assert len(summaries) == 5
    assert summaries[0].rank == 1
    assert summaries[4].rank == 5


def test_build_brief_internal_links_passed_through():
    pages = [_make_page("https://a.com")]
    analysis = _make_analysis()
    links = ["https://mysite.com/page-a", "https://mysite.com/page-b"]
    brief = build_brief("test", pages, analysis, internal_link_suggestions=links)
    assert brief.internal_link_suggestions == links
