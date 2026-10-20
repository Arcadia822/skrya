# RSSHub source reference

Enabled feed sources live in `topics/<topic>/sources.json`. Skrya supports RSS2, Atom, and RDF feeds. Source presets are suggestions and do not activate sources.

Feed collection defaults to five items per source; `max_items` can override that source limit. A live digest numbers at most 15 eligible items after repeat filtering. The full collected set remains available to raw Thread history.

## RSSHub configuration

An RSSHub source uses a relative route and an explicit list of instances. Skrya does not add public instances or rewrite the source configuration.

```json
{
  "sources": [
    {
      "id": "confirmed-news",
      "name": "Confirmed publication",
      "type": "rsshub",
      "enabled": true,
      "route": "/confirmed/news",
      "instance_urls": ["https://rsshub.example.org"],
      "timeout_ms": 3500,
      "hedge_delay_ms": 300,
      "max_items": 15,
      "fallback": {
        "capabilities": ["web_search", "news_search"],
        "queries": ["Confirmed publication topic terms"]
      }
    }
  ]
}
```

The example host and route describe configuration fields. They are not an activated source or a verified route recommendation. Confirm the publication, route, instances, and fallback scope before activation.

The existing RSSHub adapter bounds active requests to four. An instance wins only when its response parses into at least one usable feed item. Empty XML feeds, unsupported XML, and error pages do not stop other instances from returning usable articles. Losing instances do not count as separate source failures.

## Retrieval fallback

An explicit `fallback` block replaces the generated fallback queries and capabilities. Supported neutral capabilities are `web_search` and `news_search`. No provider name or credential belongs in this block.

If an existing RSSHub source has no fallback block, Skrya constructs a runtime request for that same confirmed source using its configured name and topic brief terms. Route text never enters generated queries because paths and query parameters can contain credentials; generated source IDs hash the exact configured endpoint. Skrya does not activate other sources, invent article URLs, call search providers from Python, or persist generated queries into `sources.json`.

`skrya retrieval-request --topic <topic>` includes pending source fallback records from persisted health. The read-only request uses the same `with_source_fallbacks` builder as digest collection. The Python digest result exposes its current fallback request in `DigestResult.retrieval_request`. External retrieval adapters execute requests and record their results through ingest v2.

## Health and successful collections

Health stays at the literal `topics/<topic>/source-health.json` path. Three consecutive failures mark a source degraded. Ten mark it in error and pause fetches until a 24-hour probe is due. A successful error probe changes error to degraded. The next successful collection restores ok. Disabled sources do not appear in pending fallback requests or digest health notices.

A successful parsed collection advances its source generation in `runs/<topic>/event-state.json`, including a collection served from the HTTP cache. Health mirrors that generation only after lifecycle recording succeeds. A failed, backoff-skipped, or preview collection does not persist a generation. Generations count successful collections, not network requests.

A digest puts relevant source health in one concise lead before its first section. It retains the five existing actions. Failed live sources never cause sample events to appear as real news.

## Cache and preview

Ordinary RSS and every RSSHub instance request use the HTTP cache. RSS defaults to 30 minutes for hot sources and two hours for warm sources. RSSHub defaults to 10 minutes. A positive `ttl_seconds` overrides a source TTL. `digest --force-refresh` bypasses HTTP freshness.

`digest --preview` reads existing cache and history without changing any file or directory under the data root. It does not write HTTP or translation cache entries, health, lifecycle state, digest snapshots, or Thread archives. Preview with force refresh still writes nothing.

Translation uses a non-expiring content-hash cache keyed by target language and translation provider. Default translation uses its declared default identity. An injected `translator(text)` uses persistent cache only when `IntelligenceService(..., translation_provider="<identity>")` supplies an explicit identity. Empty results, unchanged text, and failed translations do not become cache entries. Translation failure preserves the original text.

## Mixed topics and provenance

Live collection merges enabled feeds and explicitly recorded ingest events. Identical event-ID and content-hash pairs appear once. Pairs present in the last three real digest snapshots stay hidden from current brief items. Changed content is eligible again. Sample mode retains its sample behavior.

Source records retain their names, optional exact article URLs, and unknown evidence fields through events, snapshots, and raw Thread history. Plain source names are valid evidence and never receive guessed links. Thread progress chooses the first actual article URL even when a plain attribution comes first. Historical milestones still require editorial selection, a real date, and an article URL.

Digest snapshots remain immutable, and same-second digests get distinct archive names. Raw Thread history includes collected reporting before current digest visibility filtering. Legacy URL strings and equivalent structured URL records share a signature, so adopting structured records does not duplicate a historical report. A changed report body remains a separate raw historical entry.
