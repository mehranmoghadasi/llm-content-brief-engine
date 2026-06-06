"""Tests for the HTML parser module."""

from content_brief.parser import parse_page, _extract_headings, _extract_entities, Heading


SAMPLE_HTML = """
<html>
<head>
  <title>Email Marketing Automation for Agencies | ExampleTool</title>
  <meta name="description" content="Learn how to automate your email marketing as an agency.">
</head>
<body>
  <h1>Email Marketing Automation for Agencies</h1>
  <p>Agencies face unique challenges with email automation. Tools like HubSpot, Mailchimp,
     and ActiveCampaign dominate the space but come with high costs.</p>
  <h2>What Is Marketing Automation?</h2>
  <p>Marketing automation refers to software platforms and technologies that automatically
     manage marketing processes and multifunctional campaigns, across multiple channels.</p>
  <h2>Top Email Tools for Agencies</h2>
  <h3>HubSpot for Agencies</h3>
  <p>HubSpot offers CRM integration with powerful drip campaigns.</p>
  <h3>ActiveCampaign Features</h3>
  <p>ActiveCampaign is known for its behavioral trigger system.</p>
  <h2>Pricing Models Compared</h2>
  <p>Compare per-contact vs per-send pricing models from HubSpot and Mailchimp.</p>
  <script>console.log("This should not be counted");</script>
</body>
</html>
"""


def test_parse_page_returns_correct_word_count():
    result = parse_page("https://example.com", SAMPLE_HTML)
    # Visible text should be counted, script content excluded
    assert result.word_count > 40
    assert result.word_count < 300


def test_parse_page_extracts_meta():
    result = parse_page("https://example.com", SAMPLE_HTML)
    assert result.meta_title == "Email Marketing Automation for Agencies | ExampleTool"
    assert result.meta_description is not None
    assert "automate" in result.meta_description.lower()


def test_parse_page_extracts_headings():
    result = parse_page("https://example.com", SAMPLE_HTML)
    assert len(result.headings) == 6
    h1s = [h for h in result.headings if h.level == 1]
    assert len(h1s) == 1
    assert "Agencies" in h1s[0].text


def test_parse_page_extracts_h2_headings():
    result = parse_page("https://example.com", SAMPLE_HTML)
    h2s = [h for h in result.headings if h.level == 2]
    assert len(h2s) == 3
    texts = [h.text for h in h2s]
    assert any("Marketing Automation" in t for t in texts)


def test_extract_headings_order():
    """Headings should be returned in document order."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    headings = _extract_headings(soup)
    levels = [h.level for h in headings]
    assert levels[0] == 1  # H1 first


def test_extract_entities_filters_stop_words():
    text = "the email marketing automation platform sends drip campaigns"
    entities = _extract_entities(text, top_n=5)
    # Stop words like 'the' should not appear in results
    entity_strings = [e for e, _ in entities]
    assert "the" not in entity_strings


def test_parse_page_handles_empty_html():
    result = parse_page("https://example.com", "")
    assert result.word_count == 0
    assert result.headings == []


def test_parse_page_handles_malformed_html():
    malformed = "<html><h1>Test <b>heading</h1><p>content</p>"
    result = parse_page("https://example.com", malformed)
    # Should not raise — BeautifulSoup is lenient
    assert len(result.headings) >= 1
