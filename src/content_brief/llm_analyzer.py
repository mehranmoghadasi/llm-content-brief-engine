"""
llm_analyzer.py — LLM inference: synthesize SERP signals into a content brief.

Constructs a structured prompt from aggregated SERP signals and queries
the configured LLM: OpenAI GPT-4o/4o-mini, or any OpenAI-compatible endpoint
(Ollama, OpenRouter, LM Studio …) via the OPENAI_BASE_URL environment variable.
Returns a validated BriefAnalysis Pydantic model.
"""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field, field_validator

from content_brief.parser import ParsedPage

# ---------------------------------------------------------------------------
# Pydantic models for LLM response
# ---------------------------------------------------------------------------

class HeadingSuggestion(BaseModel):
    level: int = Field(..., ge=1, le=3, description="Heading level: 1, 2, or 3")
    text: str = Field(..., min_length=5, description="Heading text")
    notes: str | None = Field(None, description="Optional notes for the writer")


class CompetitorGap(BaseModel):
    topic: str = Field(..., description="Topic or angle underrepresented in top results")
    coverage_pct: int = Field(
        ..., ge=0, le=100,
        description="LLM's estimate of top-result coverage; replaced by a measured value in brief_builder"
    )
    opportunity: str = Field(..., description="Why this gap represents an opportunity")


class BriefAnalysis(BaseModel):
    """Structured content brief produced by LLM analysis."""

    keyword: str
    search_intent: str = Field(..., description="Primary search intent label and explanation")
    word_count_min: int = Field(..., gt=0)
    word_count_max: int = Field(..., gt=0)
    tone: str = Field(..., description="Recommended tone for the piece")
    heading_structure: list[HeadingSuggestion]
    entities_to_cover: list[str] = Field(
        ..., description="Named entities and topics the article must include"
    )
    competitor_gaps: list[CompetitorGap] = Field(
        ..., description="Content opportunities competitors are missing"
    )
    intro_hook_suggestions: list[str] = Field(
        ..., description="Three alternative opening hook ideas for the article"
    )
    paa_to_answer: list[str] = Field(
        ..., description="Questions the article should address"
    )
    estimated_internal_links: int = Field(
        default=0, description="Suggested number of internal links"
    )
    meta_title_suggestion: str = Field(..., description="SEO-optimized title tag suggestion")
    meta_description_suggestion: str = Field(
        ..., max_length=160, description="Meta description (≤160 chars)"
    )

    @field_validator("word_count_max")
    @classmethod
    def max_greater_than_min(cls, v: int, info: Any) -> int:
        min_val = info.data.get("word_count_min", 0)
        if v <= min_val:
            raise ValueError("word_count_max must be greater than word_count_min")
        return v


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(keyword: str, parsed_pages: list[ParsedPage]) -> str:
    """Build the analysis prompt sent to the LLM."""

    # Aggregate competitor headings
    competitor_headings_block = ""
    for i, page in enumerate(parsed_pages[:10], 1):
        h_texts = [f"  {'#' * h.level} {h.text}" for h in page.headings[:12]]
        word_count_note = f"~{page.word_count:,} words"
        competitor_headings_block += (
            f"\n--- Result {i} ({word_count_note}) ---\n" + "\n".join(h_texts) + "\n"
        )

    # Aggregate harvested questions
    all_paa: list[str] = []
    seen: set[str] = set()
    for page in parsed_pages:
        for q in page.paa_questions:
            if q.lower() not in seen:
                seen.add(q.lower())
                all_paa.append(q)
    paa_block = "\n".join(f"- {q}" for q in all_paa[:15]) or "(none found)"

    # Word count stats
    word_counts = [p.word_count for p in parsed_pages if p.word_count > 100]
    avg_wc = int(sum(word_counts) / len(word_counts)) if word_counts else 1500
    min_wc = min(word_counts) if word_counts else 800
    max_wc = max(word_counts) if word_counts else 3000

    prompt = f"""You are an expert SEO content strategist. Analyze the following SERP data for the keyword:

TARGET KEYWORD: "{keyword}"

COMPETITOR HEADING STRUCTURES:
{competitor_headings_block}

QUESTIONS FOUND ON THE TOP RESULTS (related searches, FAQ schema, question headings):
{paa_block}

WORD COUNT STATS (from top results):
- Average: {avg_wc:,} words
- Range: {min_wc:,} – {max_wc:,} words

Based on this data, produce a detailed SEO content brief as a valid JSON object matching this schema:

{{
  "keyword": "{keyword}",
  "search_intent": "<primary intent: Informational|Commercial|Transactional|Navigational + one-sentence explanation>",
  "word_count_min": <integer>,
  "word_count_max": <integer>,
  "tone": "<recommended tone: e.g. authoritative and educational, conversational, etc.>",
  "heading_structure": [
    {{"level": 1, "text": "<H1 suggestion>", "notes": "<optional note for writer>"}},
    {{"level": 2, "text": "<H2>", "notes": null}},
    ... (include all recommended H1/H2/H3 sections)
  ],
  "entities_to_cover": ["<entity 1>", "<entity 2>", ...],
  "competitor_gaps": [
    {{
      "topic": "<topic or angle>",
      "coverage_pct": <0-100>,
      "opportunity": "<one sentence on why this is an opportunity>"
    }},
    ...
  ],
  "intro_hook_suggestions": [
    "<hook idea 1>",
    "<hook idea 2>",
    "<hook idea 3>"
  ],
  "paa_to_answer": ["<question 1>", "<question 2>", ...],
  "estimated_internal_links": <integer, typical 2-5>,
  "meta_title_suggestion": "<SEO-optimized title tag, ≤60 chars>",
  "meta_description_suggestion": "<meta description, ≤160 chars>"
}}

Rules:
- Return ONLY valid JSON, no markdown fences, no commentary.
- word_count_min and word_count_max should be realistic given the competitor data.
- Include at least 8 heading_structure entries.
- entities_to_cover should list 8-15 specific named entities, tools, concepts.
- competitor_gaps should include 3-5 genuine content differentiation opportunities; name each topic with the concrete words a page covering it would use.
- paa_to_answer should include the most relevant questions from the list above.
"""
    return prompt


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def estimate_tokens(prompt: str) -> int:
    """Rough token estimate (4 chars per token on average)."""
    return len(prompt) // 4


def analyze_with_llm(
    keyword: str,
    parsed_pages: list[ParsedPage],
    model: str | None = None,
    dry_run: bool = False,
) -> BriefAnalysis:
    """
    Send aggregated SERP signals to the LLM and return a BriefAnalysis.

    Args:
        keyword: The target keyword.
        parsed_pages: List of ParsedPage objects from the parser module.
        model: OpenAI model identifier (default: from OPENAI_MODEL env var or gpt-4o-mini).
        dry_run: If True, skip the API call and return a cost estimate stub.

    Returns:
        BriefAnalysis — the validated LLM-generated brief data.

    Raises:
        ValueError: If the LLM returns malformed JSON that can't be validated.
        RuntimeError: If OPENAI_API_KEY is missing.
    """
    resolved_model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY environment variable not set. "
            "Add it to your .env file or export it in your shell."
        )

    prompt = _build_prompt(keyword, parsed_pages)
    estimated = estimate_tokens(prompt)

    if dry_run:
        # Return a stub BriefAnalysis with cost information
        cost_per_1k = 0.00015 if "mini" in resolved_model else 0.005
        cost_estimate = round((estimated / 1000) * cost_per_1k, 5)
        print(
            f"\nDRY RUN — no API call made.\n"
            f"  Model:            {resolved_model}\n"
            f"  Estimated tokens: ~{estimated:,} input + ~1,800 output\n"
            f"  Approx cost:      ${cost_estimate}\n"
        )
        raise SystemExit(0)

    client = OpenAI(api_key=api_key, base_url=os.getenv("OPENAI_BASE_URL") or None)

    try:
        response = client.chat.completions.create(
            model=resolved_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert SEO content strategist. "
                        "Always respond with valid JSON only. No markdown, no prose."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=2048,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        raise RuntimeError(f"LLM API call failed: {exc}") from exc

    raw_json = response.choices[0].message.content or "{}"

    try:
        data = json.loads(raw_json)
        # Inject keyword in case LLM omits it
        data.setdefault("keyword", keyword)
        return BriefAnalysis.model_validate(data)
    except (json.JSONDecodeError, Exception) as exc:
        raise ValueError(
            f"LLM returned invalid/unvalidatable JSON: {exc}\n\nRaw response:\n{raw_json[:500]}"
        ) from exc
