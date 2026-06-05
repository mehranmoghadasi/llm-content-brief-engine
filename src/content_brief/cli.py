"""
cli.py — Click-based CLI for llm-content-brief-engine.

Commands:
  brief generate  — Generate a content brief for a keyword.
  brief list      — List recently generated briefs.
  brief version   — Print version.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from content_brief import __version__
from content_brief.crawler import fetch_serp_and_pages
from content_brief.llm_analyzer import analyze_with_llm
from content_brief.parser import parse_all_pages
from content_brief.brief_builder import build_brief
from content_brief.renderer import render_json, render_markdown, render_html

load_dotenv()

console = Console()

_DEFAULT_OUTPUT_DIR = Path("output")
_DEFAULT_TEMPLATE_DIR = Path(__file__).parent.parent.parent / "templates"


def _resolve_template_dir(explicit: Optional[Path] = None) -> Path:
    """Find the templates directory relative to the package install location."""
    if explicit:
        return explicit
    # Try package-adjacent templates dir
    candidate = Path(__file__).parent.parent.parent / "templates"
    if candidate.exists():
        return candidate
    # Fallback: cwd/templates
    return Path("templates")


@click.group()
@click.version_option(__version__, prog_name="brief")
def cli() -> None:
    """llm-content-brief-engine — Generate SEO content briefs from SERP + LLM analysis."""
    pass


@cli.command("generate")
@click.option("--keyword", "-k", required=True, help="Target keyword for the content brief.")
@click.option(
    "--output-dir", "-o",
    default=str(_DEFAULT_OUTPUT_DIR),
    show_default=True,
    help="Directory to save output files.",
)
@click.option(
    "--model", "-m",
    default=None,
    help="OpenAI model (default: OPENAI_MODEL env var or gpt-4o-mini).",
)
@click.option(
    "--max-results", "-n",
    default=10,
    show_default=True,
    type=click.IntRange(1, 20),
    help="Number of SERP results to crawl.",
)
@click.option(
    "--sitemap",
    default=None,
    help="Optional sitemap URL for internal link suggestions.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Estimate cost without making an LLM API call.",
)
@click.option(
    "--crawl-delay",
    default=0.8,
    show_default=True,
    type=float,
    help="Seconds between page fetches (default 0.8).",
)
def generate_command(
    keyword: str,
    output_dir: str,
    model: Optional[str],
    max_results: int,
    sitemap: Optional[str],
    dry_run: bool,
    crawl_delay: float,
) -> None:
    """Generate a structured SEO content brief for KEYWORD."""

    out_path = Path(output_dir)

    console.print(
        Panel.fit(
            f"[bold cyan]llm-content-brief-engine[/bold cyan]  v{__version__}\n"
            f"Keyword: [bold]{keyword}[/bold]",
            border_style="cyan",
        )
    )

    # --- Phase 1: SERP crawl ---
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching SERP results + crawling pages…", total=None)
        serp_result = asyncio.run(
            fetch_serp_and_pages(keyword, max_results=max_results, crawl_delay_s=crawl_delay)
        )
        progress.update(task, description=f"✓ Crawled {len(serp_result.pages)} pages")

    # --- Phase 2: Parse pages ---
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Parsing headings, entities, PAA…", total=None)
        parsed_pages = parse_all_pages(serp_result.pages)
        progress.update(task, description=f"✓ Parsed {len(parsed_pages)} pages")

    if not parsed_pages:
        console.print(
            "[red]No pages could be parsed. Check network access and try again.[/red]"
        )
        raise SystemExit(1)

    # --- Phase 3: LLM analysis ---
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Running LLM analysis…", total=None)
        try:
            analysis = analyze_with_llm(
                keyword=keyword,
                parsed_pages=parsed_pages,
                model=model,
                dry_run=dry_run,
            )
        except RuntimeError as exc:
            console.print(f"[red]LLM error: {exc}[/red]")
            raise SystemExit(1)
        except ValueError as exc:
            console.print(f"[yellow]LLM response could not be fully validated: {exc}[/yellow]")
            raise SystemExit(1)
        progress.update(task, description="✓ LLM analysis complete")

    # --- Phase 4: Build BriefModel ---
    brief = build_brief(
        keyword=keyword,
        parsed_pages=parsed_pages,
        analysis=analysis,
        sitemap_url=sitemap,
    )

    # --- Phase 5: Render outputs ---
    template_dir = _DEFAULT_TEMPLATE_DIR

    json_path = render_json(brief, out_path)
    md_path = render_markdown(brief, out_path)

    if template_dir.exists():
        html_path = render_html(brief, out_path, template_dir)
        html_note = str(html_path)
    else:
        html_path = None
        html_note = "[dim](skipped — templates/ dir not found)[/dim]"

    # --- Summary table ---
    table = Table(title="Brief Summary", show_header=True, header_style="bold cyan")
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("Keyword", brief.keyword)
    table.add_row("Search intent", brief.search_intent[:80])
    table.add_row("Word count target", f"{brief.word_count_min:,} – {brief.word_count_max:,}")
    table.add_row("Tone", brief.tone)
    table.add_row("Headings suggested", str(len(brief.heading_structure)))
    table.add_row("Entities to cover", str(len(brief.entities_to_cover)))
    table.add_row("Competitor gaps", str(len(brief.competitor_gaps)))
    table.add_row("PAA questions", str(len(brief.paa_to_answer)))
    table.add_row("Competitors analyzed", str(len(brief.competitors)))
    console.print(table)

    console.print("\n[bold green]Output files:[/bold green]")
    console.print(f"  JSON:     {json_path}")
    console.print(f"  Markdown: {md_path}")
    console.print(f"  HTML:     {html_note}")


@cli.command("list")
@click.option(
    "--output-dir", "-o",
    default=str(_DEFAULT_OUTPUT_DIR),
    show_default=True,
    help="Directory to scan for existing briefs.",
)
def list_command(output_dir: str) -> None:
    """List recently generated content briefs."""
    out_path = Path(output_dir)
    if not out_path.exists():
        console.print(f"[yellow]Output directory not found: {out_path}[/yellow]")
        return

    briefs = sorted(out_path.glob("brief_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not briefs:
        console.print("[dim]No briefs found. Run `brief generate` to create one.[/dim]")
        return

    table = Table(title=f"Briefs in {out_path}", show_header=True)
    table.add_column("#")
    table.add_column("File")
    table.add_column("Size")
    for i, b in enumerate(briefs[:20], 1):
        size = f"{b.stat().st_size // 1024} KB"
        table.add_row(str(i), b.name, size)

    console.print(table)


# Allow Optional usage before importing
from typing import Optional  # noqa: E402


if __name__ == "__main__":
    cli()
