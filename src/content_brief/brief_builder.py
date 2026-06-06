"""
brief_builder.py — Assemble the final BriefModel from crawled signals + LLM analysis.

Acts as the composition layer: takes ParsedPages + BriefAnalysis and produces
a rich BriefModel that carries everything the renderers need.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from content_brief.llm_analyzer import BriefAnalysis
from content_brief.parser import ParsedPage


@dataclass
class CompetitorSummary:
    """Light summary of a single competitor page."""

    rank: int
    url: str
    meta_title: Optional[str]
    word_count: int
    h2_headings: list[str]


@dataclass
class BriefModel:
    """Complete, render-ready content brief model."""

    # Identity
    keyword: str
    generated_at: str  # ISO 8601 timestamp

    # LLM-derived fields
    search_intent: str
    word_count_min: int
    word_count_max: int
    tone: str
    heading_structure: list[dict]          # [{level, text, notes}]
    entities_to_cover: list[str]
    competitor_gaps: list[dict]            # [{topic, coverage_pct, opportunity}]
    intro_hook_suggestions: list[str]
    paa_to_answer: list[str]
    meta_title_suggestion: str
    meta_description_suggestion: str

    # Aggregated SERP signals
    competitors: list[CompetitorSummary]
    top_entities_across_results: list[tuple[str, int]]   # (entity, freq)
    all_paa_questions: list[str]
    avg_competitor_word_count: int

    # Optional
    internal_link_suggestions: list[str] = field(default_factory=list)
    sitemap_url: Optional[str] = None


def _aggregate_entities(parsed_pages: list[ParsedPage], top_n: int = 20) -> list[tuple[str, int]]:
    """Merge entity frequency counts across all parsed pages."""
    total: Counter = Counter()
    for page in parsed_pages:
        for entity, freq in page.top_entities:
            total[entity] += 1  # count pages that mention it, not raw frequency
    return total.most_common(top_n)


def _aggregate_paa(parsed_pages: list[ParsedPage]) -> list[str]:
    """Collect unique PAA questions from all pages."""
    seen: set[str] = set()
    result: list[str] = []
    for page in parsed_pages:
        for q in page.paa_questions:
            key = q.lower().strip()
            if key not in seen and len(q) > 10:
                seen.add(key)
                result.append(q)
    return result


def _build_competitor_summaries(parsed_pages: list[ParsedPage]) -> list[CompetitorSummary]:
    """Build ranked competitor summary list."""
    summaries: list[CompetitorSummary] = []
    for i, page in enumerate(parsed_pages, 1):
        h2s = [h.text for h in page.headings if h.level == 2][:6]
        summaries.append(
            CompetitorSummary(
                rank=i,
                url=page.url,
                meta_title=page.meta_title,
                word_count=page.word_count,
                h2_headings=h2s,
            )
        )
    return summaries


def build_brief(
    keyword: str,
    parsed_pages: list[ParsedPage],
    analysis: BriefAnalysis,
    internal_link_suggestions: Optional[list[str]] = None,
    sitemap_url: Optional[str] = None,
) -> BriefModel:
    """
    Compose the final BriefModel from parsed pages and LLM analysis.

    Args:
        keyword: Target keyword string.
        parsed_pages: Pages parsed by the parser module.
        analysis: BriefAnalysis returned by the LLM analyzer.
        internal_link_suggestions: Optional list of internal URLs suggested from sitemap.
        sitemap_url: The sitemap URL used for internal link lookup (for display).

    Returns:
        BriefModel ready to be passed to renderers.
    """
    competitors = _build_competitor_summaries(parsed_pages)
    top_entities = _aggregate_entities(parsed_pages)
    all_paa = _aggregate_paa(parsed_pages)

    # Average competitor word count (only pages with meaningful content)
    word_counts = [p.word_count for p in parsed_pages if p.word_count > 200]
    avg_wc = int(sum(word_counts) / len(word_counts)) if word_counts else 0

    heading_structure = [h.model_dump() for h in analysis.heading_structure]
    competitor_gaps = [g.model_dump() for g in analysis.competitor_gaps]

    return BriefModel(
        keyword=keyword,
        generated_at=datetime.now(timezone.utc).isoformat(),
        search_intent=analysis.search_intent,
        word_count_min=analysis.word_count_min,
        word_count_max=analysis.word_count_max,
        tone=analysis.tone,
        heading_structure=heading_structure,
        entities_to_cover=analysis.entities_to_cover,
        competitor_gaps=competitor_gaps,
        intro_hook_suggestions=analysis.intro_hook_suggestions,
        paa_to_answer=analysis.paa_to_answer,
        meta_title_suggestion=analysis.meta_title_suggestion,
        meta_description_suggestion=analysis.meta_description_suggestion,
        competitors=competitors,
        top_entities_across_results=top_entities,
        all_paa_questions=all_paa,
        avg_competitor_word_count=avg_wc,
        internal_link_suggestions=internal_link_suggestions or [],
        sitemap_url=sitemap_url,
    )
