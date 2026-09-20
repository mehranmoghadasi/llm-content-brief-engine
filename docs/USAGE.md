# Usage

## Generate a brief

```bash
brief generate -k "calgary rental market outlook" --max-results 8 --output-dir output/
```

Phases: SERP fetch → page crawl (robots-aware, `--crawl-delay` seconds between pages) → parse → LLM analysis → measured gap check → render `.json`, `.md`, `.html`.

## Internal links from your own sitemap

```bash
brief generate -k "calgary rental market outlook" --sitemap https://yoursite.com/sitemap.xml
```

The sitemap (or sitemap index) is fetched and every URL is scored by how many content words of the keyword (weight 2) and the suggested headings (weight 1) appear in its slug. The top 8 land in the brief's "Internal Linking Suggestions" section with the matched words shown, so the writer can judge relevance at a glance.

## Cost check before spending tokens

```bash
brief generate -k "..." --dry-run
```

Prints the token estimate for the prompt and exits without calling the API.

## Using a local or alternative model

The tool speaks the OpenAI chat-completions protocol. Point it at any compatible server:

```bash
export OPENAI_BASE_URL=http://localhost:11434/v1   # Ollama
export OPENAI_API_KEY=ollama                       # any non-empty string for local servers
brief generate -k "..." --model llama3.1
```

Responses must be valid JSON matching the brief schema; smaller models sometimes fail validation, in which case the CLI reports the error and exits 1 rather than writing a half-empty brief.

## Reading the gap section

Each gap shows *measured* coverage: the share of crawled pages whose text or headings contain the topic's content words. The LLM's original estimate is preserved in the JSON output as `llm_estimate_pct` so you can see where it was wrong. Topics covered by more than half the SERP are removed — they are requirements, not opportunities.

## Environment

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | required |
| `OPENAI_MODEL` | default model (CLI `--model` overrides) |
| `OPENAI_BASE_URL` | optional OpenAI-compatible endpoint |
