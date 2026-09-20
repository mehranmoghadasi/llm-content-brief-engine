"""Sitemap parsing and internal-link ranking (no network)."""

import httpx
import pytest

from content_brief.sitemap import (
    fetch_sitemap_urls,
    parse_sitemap,
    slug_tokens,
    suggest_internal_links,
)

INDEX = '<sitemapindex xmlns="x"><sitemap><loc>https://s.com/a.xml</loc></sitemap></sitemapindex>'
URLSET = ('<urlset><url><loc>https://s.com/blog/calgary-rental-market-2026</loc></url>'
          '<url><loc>https://s.com/services/property-management</loc></url>'
          '<url><loc>https://s.com/about?a=1&amp;b=2</loc></url></urlset>')


def test_parse_sitemap_index_vs_urlset():
    assert parse_sitemap(INDEX) == (True, ["https://s.com/a.xml"])
    is_index, urls = parse_sitemap(URLSET)
    assert not is_index and urls[-1] == "https://s.com/about?a=1&b=2"


@pytest.mark.asyncio
async def test_fetch_sitemap_urls_recurses_index():
    def handler(request):
        body = INDEX if request.url.path == "/i.xml" else URLSET
        return httpx.Response(200, text=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        urls = await fetch_sitemap_urls("https://s.com/i.xml", client)
    assert len(urls) == 3 and urls[0].endswith("calgary-rental-market-2026")


def test_suggest_internal_links_ranks_by_slug_overlap():
    urls = ["https://s.com/blog/calgary-rental-market-2026", "https://s.com/services/property-management",
            "https://s.com/about", "https://s.com/blog/tenant-screening"]
    out = suggest_internal_links("calgary rental market", ["Tenant screening tips", "Property management fees"], urls)
    assert out[0]["url"].endswith("calgary-rental-market-2026") and out[0]["score"] == 6
    assert {o["url"] for o in out} == {urls[0], urls[1], urls[3]}  # /about has no overlap
    assert slug_tokens("https://s.com/a-b/cde") == {"cde"}
