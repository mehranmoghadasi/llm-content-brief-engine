"""
crawler.py — SERP URL discovery and per-page HTML fetching.

Fetches top-N organic URLs for a keyword, then downloads each page
for downstream parsing. Respects robots.txt, applies crawl delay,
and uses exponential backoff on transient failures.
"""

from __future__ import annotations

import asyncio
import time
import urllib.parse
import urllib.robotparser
from dataclasses import dataclass, field

import httpx
from bs4 import BeautifulSoup
from rich.console import Console

console = Console()

# User-agent presented to sites during crawling
_UA = (
    "Mozilla/5.0 (compatible; llm-content-brief-engine/0.4; "
    "+https://github.com/mehranmoghadasi/llm-content-brief-engine)"
)
_HEADERS = {"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"}

# DuckDuckGo HTML search endpoint (no API key required)
_DDG_SEARCH_URL = "https://html.duckduckgo.com/html/?q={query}&kl=us-en"


@dataclass
class PageResult:
    """Holds raw data for a single crawled page."""

    url: str
    html: str
    status_code: int
    fetch_time_ms: float
    error: str | None = None


@dataclass
class SerpFetchResult:
    """All organic URLs found for a keyword plus page HTML."""

    keyword: str
    organic_urls: list[str] = field(default_factory=list)
    pages: list[PageResult] = field(default_factory=list)


def _parse_ddg_organic_urls(html: str, max_results: int) -> list[str]:
    """Extract organic result URLs from DuckDuckGo HTML response."""
    soup = BeautifulSoup(html, "lxml")
    urls: list[str] = []
    for result in soup.select("a.result__a"):
        href = result.get("href", "")
        # DDG wraps links — follow redirects or extract uddg param
        if href.startswith("/l/?"):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            actual = qs.get("uddg", [None])[0]
            if actual:
                href = urllib.parse.unquote(actual)
        if href.startswith("http") and href not in urls:
            urls.append(href)
        if len(urls) >= max_results:
            break
    return urls


def _is_allowed_by_robots(url: str, user_agent: str = "*") -> bool:
    """Returns True if robots.txt permits crawling the URL."""
    parsed = urllib.parse.urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
        return rp.can_fetch(user_agent, url)
    except (OSError, ValueError):
        # If robots.txt is unreachable or malformed, assume allowed
        return True


async def _fetch_url(
    client: httpx.AsyncClient,
    url: str,
    retries: int = 3,
    backoff_base: float = 1.5,
) -> PageResult:
    """Download a single URL with retry + exponential backoff."""
    last_error: str | None = None
    for attempt in range(retries):
        try:
            t0 = time.monotonic()
            response = await client.get(url, follow_redirects=True, timeout=15.0)
            elapsed = (time.monotonic() - t0) * 1000
            if response.status_code == 200:
                return PageResult(
                    url=str(response.url),
                    html=response.text,
                    status_code=response.status_code,
                    fetch_time_ms=round(elapsed, 1),
                )
            last_error = f"HTTP {response.status_code}"
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            last_error = str(exc)

        if attempt < retries - 1:
            await asyncio.sleep(backoff_base ** attempt)

    return PageResult(
        url=url,
        html="",
        status_code=0,
        fetch_time_ms=0.0,
        error=last_error,
    )


async def fetch_serp_and_pages(
    keyword: str,
    max_results: int = 10,
    crawl_delay_s: float = 0.8,
) -> SerpFetchResult:
    """
    Main entry point: fetches SERP URLs for ``keyword`` then downloads each page.

    Args:
        keyword: Target keyword for which to generate a content brief.
        max_results: Maximum number of organic results to retrieve (default 10).
        crawl_delay_s: Seconds to wait between page fetches (default 0.8).

    Returns:
        SerpFetchResult containing all discovered URLs and their page HTML.
    """
    result = SerpFetchResult(keyword=keyword)

    async with httpx.AsyncClient(headers=_HEADERS) as client:
        # Step 1: fetch SERP page from DuckDuckGo
        query_encoded = urllib.parse.quote_plus(keyword)
        serp_url = _DDG_SEARCH_URL.format(query=query_encoded)
        console.log(f"[dim]Fetching SERP: {serp_url}[/dim]")

        try:
            serp_resp = await client.get(serp_url, follow_redirects=True, timeout=20.0)
            if serp_resp.status_code != 200:
                console.print(
                    f"[yellow]SERP returned {serp_resp.status_code}; "
                    "results may be limited[/yellow]"
                )
                return result
            organic_urls = _parse_ddg_organic_urls(serp_resp.text, max_results)
        except (httpx.HTTPError, ValueError) as exc:
            console.print(f"[red]SERP fetch failed: {exc}[/red]")
            return result

        result.organic_urls = organic_urls
        console.log(f"[dim]Found {len(organic_urls)} organic URLs[/dim]")

        # Step 2: fetch each page with delay (robots-aware)
        for i, url in enumerate(organic_urls):
            if not _is_allowed_by_robots(url, user_agent=_UA):
                console.log(f"[dim]Skipping (robots.txt): {url}[/dim]")
                continue

            page = await _fetch_url(client, url)
            if page.error:
                console.log(f"[yellow]Error fetching {url}: {page.error}[/yellow]")
            else:
                console.log(
                    f"[dim]Fetched [{i + 1}/{len(organic_urls)}] "
                    f"{url} ({page.fetch_time_ms:.0f}ms)[/dim]"
                )
            result.pages.append(page)

            # Respectful crawl delay between pages
            if i < len(organic_urls) - 1:
                await asyncio.sleep(crawl_delay_s)

    return result
