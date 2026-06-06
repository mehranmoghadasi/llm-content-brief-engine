"""
renderer.py — Render BriefModel to JSON, Markdown, and HTML output files.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from content_brief.brief_builder import BriefModel


def _slug(text: str) -> str:
    """Convert a keyword into a filesystem-safe slug."""
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_-]+", "-", slug).strip("-")
    return slug[:60]


def render_json(brief: BriefModel, output_dir: Path) -> Path:
    """Serialize the BriefModel as pretty-printed JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"brief_{_slug(brief.keyword)}.json"
    out_path = output_dir / filename

    # Convert dataclass + nested dataclasses to dict
    data = {
        "keyword": brief.keyword,
        "generated_at": brief.generated_at,
        "search_intent": brief.search_intent,
        "word_count_range": {"min": brief.word_count_min, "max": brief.word_count_max},
        "tone": brief.tone,
        "meta_title_suggestion": brief.meta_title_suggestion,
        "meta_description_suggestion": brief.meta_description_suggestion,
        "heading_structure": brief.heading_structure,
        "entities_to_cover": brief.entities_to_cover,
        "competitor_gaps": brief.competitor_gaps,
        "intro_hook_suggestions": brief.intro_hook_suggestions,
        "paa_to_answer": brief.paa_to_answer,
        "internal_link_suggestions": brief.internal_link_suggestions,
        "avg_competitor_word_count": brief.avg_competitor_word_count,
        "competitors": [
            {
                "rank": c.rank,
                "url": c.url,
                "meta_title": c.meta_title,
                "word_count": c.word_count,
                "h2_headings": c.h2_headings,
            }
            for c in brief.competitors
        ],
        "top_entities_across_results": [
            {"entity": e, "page_count": n} for e, n in brief.top_entities_across_results
        ],
    }

    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)

    return out_path


def render_markdown(brief: BriefModel, output_dir: Path) -> Path:
    """Render the BriefModel as a structured Markdown document."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"brief_{_slug(brief.keyword)}.md"
    out_path = output_dir / filename

    lines: list[str] = []
    lines.append(f"# SEO Content Brief: {brief.keyword}\n")
    lines.append(f"**Generated:** {brief.generated_at}  \n")
    lines.append(f"**Avg competitor word count:** {brief.avg_competitor_word_count:,}\n\n")

    lines.append("---\n\n## Brief Overview\n\n")
    lines.append(f"| Field | Value |\n|---|---|\n")
    lines.append(f"| Target keyword | `{brief.keyword}` |\n")
    lines.append(f"| Search intent | {brief.search_intent} |\n")
    lines.append(
        f"| Recommended word count | {brief.word_count_min:,} – {brief.word_count_max:,} |\n"
    )
    lines.append(f"| Tone | {brief.tone} |\n")
    lines.append(f"| Meta title | {brief.meta_title_suggestion} |\n")
    lines.append(f"| Meta description | {brief.meta_description_suggestion} |\n\n")

    lines.append("---\n\n## Recommended Heading Structure\n\n")
    for h in brief.heading_structure:
        prefix = "#" * h["level"]
        note = f"  _{h['notes']}_" if h.get("notes") else ""
        lines.append(f"{prefix} {h['text']}{note}\n\n")

    lines.append("---\n\n## Entities & Topics to Cover\n\n")
    for entity in brief.entities_to_cover:
        lines.append(f"- {entity}\n")
    lines.append("\n")

    lines.append("---\n\n## Competitor Gap Opportunities\n\n")
    for gap in brief.competitor_gaps:
        lines.append(
            f"**{gap['topic']}** _(covered by {gap['coverage_pct']}% of results)_  \n"
            f"{gap['opportunity']}\n\n"
        )

    lines.append("---\n\n## People Also Ask — Address These\n\n")
    for q in brief.paa_to_answer:
        lines.append(f"- {q}\n")
    lines.append("\n")

    lines.append("---\n\n## Intro Hook Ideas\n\n")
    for i, hook in enumerate(brief.intro_hook_suggestions, 1):
        lines.append(f"**Option {i}:** {hook}\n\n")

    if brief.internal_link_suggestions:
        lines.append("---\n\n## Internal Linking Suggestions\n\n")
        for link in brief.internal_link_suggestions:
            lines.append(f"- {link}\n")
        lines.append("\n")

    lines.append("---\n\n## Competitor Analysis\n\n")
    for c in brief.competitors[:5]:
        lines.append(f"### #{c.rank} — [{c.meta_title or c.url}]({c.url})\n\n")
        lines.append(f"**Word count:** ~{c.word_count:,}  \n")
        lines.append(f"**H2 sections:** {', '.join(c.h2_headings) or 'N/A'}\n\n")

    with out_path.open("w", encoding="utf-8") as fh:
        fh.writelines(lines)

    return out_path


def render_html(brief: BriefModel, output_dir: Path, template_dir: Path) -> Path:
    """Render the BriefModel as a styled HTML document via Jinja2."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"brief_{_slug(brief.keyword)}.html"
    out_path = output_dir / filename

    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("brief.html.j2")
    rendered = template.render(brief=brief)

    with out_path.open("w", encoding="utf-8") as fh:
        fh.write(rendered)

    return out_path
