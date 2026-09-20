"""
sitemap.py — Suggest internal links from your own sitemap.

Fetches an XML sitemap (recursing into sitemap indexes), then ranks URLs by how
many of the target keyword's and suggested headings' content words appear in
the URL slug. No dependencies beyond httpx.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

from content_brief.gaps import significant_tokens

_LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.IGNORECASE)
_UA = "llm-content-brief-engine/0.4 (+https://github.com/mehranmoghadasi/llm-content-brief-engine)"


def parse_sitemap(xml: str) -> tuple[bool, list[str]]:
    """Return (is_index, urls)."""
    urls = [u.replace("&amp;", "&") for u in _LOC_RE.findall(xml)]
    return bool(re.search(r"<sitemapindex[\s>]", xml, re.IGNORECASE)), urls


async def fetch_sitemap_urls(sitemap_url: str, client: httpx.AsyncClient, max_sitemaps: int = 25, max_urls: int = 20000) -> list[str]:
    """Collect page URLs from a sitemap or sitemap index."""
    queue, seen, pages = [sitemap_url], set(), []
    while queue and len(seen) < max_sitemaps and len(pages) < max_urls:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            resp = await client.get(url, headers={"user-agent": _UA}, follow_redirects=True, timeout=20.0)
            if resp.status_code != 200:
                continue
        except httpx.HTTPError:
            continue
        is_index, urls = parse_sitemap(resp.text)
        if is_index:
            queue.extend(urls)
        else:
            pages.extend(urls)
    return pages


def slug_tokens(url: str) -> set[str]:
    path = urlparse(url).path.lower()
    return {t for t in re.split(r"[^a-z0-9]+", path) if len(t) >= 3}


def suggest_internal_links(keyword: str, headings: list[str], urls: list[str], top_n: int = 8) -> list[dict]:
    """Rank sitemap URLs by slug overlap with the keyword (weight 2) and headings (weight 1).

    Returns [{url, score, matched}] — only URLs with at least one match.
    """
    kw_tokens = set(significant_tokens(keyword))
    heading_tokens: set[str] = set()
    for h in headings:
        heading_tokens.update(significant_tokens(h))
    heading_tokens -= kw_tokens
    scored = []
    for url in urls:
        slug = slug_tokens(url)
        kw_hits = slug & kw_tokens
        h_hits = slug & heading_tokens
        score = 2 * len(kw_hits) + len(h_hits)
        if score:
            scored.append({"url": url, "score": score, "matched": sorted(kw_hits | h_hits)})
    scored.sort(key=lambda s: (-s["score"], s["url"]))
    return scored[:top_n]
