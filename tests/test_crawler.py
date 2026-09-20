"""SERP URL extraction and robots handling (no network)."""

from unittest.mock import patch

from content_brief.crawler import _is_allowed_by_robots, _parse_ddg_organic_urls

DDG = """
<html><body>
<a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.com%2Fguide&amp;rut=1">Guide</a>
<a class="result__a" href="https://direct.example.org/page">Direct</a>
<a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.com%2Fguide">Duplicate</a>
<a class="result__a" href="javascript:void(0)">Junk</a>
</body></html>
"""


def test_parse_ddg_unwraps_redirects_dedupes_and_caps():
    urls = _parse_ddg_organic_urls(DDG, max_results=10)
    assert urls == ["https://example.com/guide", "https://direct.example.org/page"]
    assert _parse_ddg_organic_urls(DDG, max_results=1) == ["https://example.com/guide"]


def test_robots_disallow_is_respected():
    class FakeParser:
        def __init__(self, allowed):
            self.allowed = allowed

        def set_url(self, url):
            pass

        def read(self):
            pass

        def can_fetch(self, ua, url):
            return self.allowed

    with patch("content_brief.crawler.urllib.robotparser.RobotFileParser", lambda: FakeParser(False)):
        assert _is_allowed_by_robots("https://x.com/private") is False
    with patch("content_brief.crawler.urllib.robotparser.RobotFileParser", lambda: FakeParser(True)):
        assert _is_allowed_by_robots("https://x.com/public") is True
