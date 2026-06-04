# Architecture — llm-content-brief-engine

## Overview

The tool is a sequential data pipeline with five stages, each implemented as an independent module:

```
crawler → parser → llm_analyzer → brief_builder → renderer
```

Each stage has a well-defined input/output contract, making individual stages testable in isolation and replaceable (e.g. swapping DuckDuckGo for SerpAPI without touching the parser).

## Stage Details

### 1. Crawler (`crawler.py`)

- **Input:** keyword string, max_results, crawl_delay
- **Output:** `SerpFetchResult` containing organic URLs + raw page HTML

Fetches the SERP from DuckDuckGo HTML (no API key required) by sending a standard browser User-Agent. Then downloads each organic URL with async httpx, respecting `robots.txt` and applying exponential backoff on failures.

**Key design choices:**
- `asyncio` + `httpx.AsyncClient` for non-blocking HTTP — crawling 10 pages takes ~5–8 seconds with 0.8s delay vs ~20s+ synchronously
- Robots.txt check before each fetch prevents targeting pages that disallow crawlers
- Backoff base 1.5 (not aggressive) — balances retry resilience with avoiding rate limiting

### 2. Parser (`parser.py`)

- **Input:** list of `PageResult` (url + raw HTML)
- **Output:** list of `ParsedPage` (structured signals)

Uses BeautifulSoup + lxml for fast HTML parsing. Extracts heading hierarchy, visible word count (excluding scripts/styles/nav), frequency-based entity candidates (bigrams + trigrams after stop-word filtering), and PAA questions.

**Key design choices:**
- No NLP model dependency — entity extraction is frequency-based. The LLM in stage 3 does deeper semantic understanding; the parser just aggregates raw signals.
- `_IGNORED_TAGS` set prevents nav/footer/script text inflating word counts
- PAA extraction handles DuckDuckGo related-searches, FAQ schema markup, and question-containing headings as multiple extraction strategies

### 3. LLM Analyzer (`llm_analyzer.py`)

- **Input:** keyword + list of `ParsedPage`
- **Output:** `BriefAnalysis` (Pydantic-validated brief data from LLM)

Constructs a structured prompt containing competitor headings, PAA questions, and word count stats. Sends to OpenAI API with `response_format: json_object` for deterministic JSON output. Validates the response with Pydantic v2.

**Key design choices:**
- `json_object` response format eliminates markdown-wrapping of JSON — more reliable than parsing fenced code blocks
- Pydantic validation ensures the LLM response matches the expected schema; fields that fail validation surface a clear error rather than silently corrupting downstream output
- `temperature=0.3` — low enough for structured/consistent output, high enough to avoid mechanical heading suggestions
- Dry-run mode estimates cost before any API call — important for agencies running this in automated pipelines

### 4. Brief Builder (`brief_builder.py`)

- **Input:** `ParsedPage` list + `BriefAnalysis`
- **Output:** `BriefModel` (complete render-ready data model)

Acts as the composition layer. Aggregates entity frequencies across pages (counting pages that mention an entity, not raw occurrences — normalizes for page length differences). Deduplicates PAA questions case-insensitively. Computes average competitor word count from pages with >200 words to exclude stub pages.

### 5. Renderer (`renderer.py`)

- **Input:** `BriefModel` + output directory + optional template directory
- **Output:** `.json`, `.md`, `.html` files

Three render paths, each independent:
- **JSON:** raw data for programmatic consumption / pipeline integration
- **Markdown:** human-readable, compatible with CMS paste-in
- **HTML:** Jinja2-rendered, self-contained, styled for sharing with writers

## Error Handling Strategy

| Stage | Failure Mode | Behavior |
|---|---|---|
| Crawler — SERP fetch | Network error | Returns empty result, CLI prints error |
| Crawler — page fetch | Timeout / HTTP error | Page skipped (non-fatal), warning printed |
| Parser | Malformed HTML | Page skipped, BeautifulSoup handles gracefully |
| LLM Analyzer | API error | RuntimeError propagated to CLI, exits with code 1 |
| LLM Analyzer | Invalid JSON response | ValueError propagated, raw response shown |
| Renderer | Template not found | HTML render skipped, JSON + MD still produced |

## Extension Points

- **SERP providers:** Replace `_parse_ddg_organic_urls` in `crawler.py` with SerpAPI, Brave Search, or Google CSE adapters — the rest of the pipeline is unaffected.
- **LLM providers:** The `analyze_with_llm` function uses the OpenAI SDK, which supports any OpenAI-compatible API endpoint. Anthropic Claude can be accessed via the OpenAI-compatible Messages API.
- **Output formats:** Add new renderers to `renderer.py` — the `BriefModel` dataclass is the stable contract.
