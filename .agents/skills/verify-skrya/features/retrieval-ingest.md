# Retrieval and ingest

For topics whose sources need runtime retrieval (web/news search, X, etc.), Skrya emits a provider-neutral retrieval request, the agent fetches with whatever tool it has, then records a normalized `skrya.ingest.v1` payload. The next digest uses those items and reports the scan window from their `fetched_at` times.

## Sub-features

- `rr-request` prints a `skrya.retrieval-request.v1` JSON with capabilities, queries, languages, max_items.
- `ingest-record` writes `runs/<topic>/ingest/latest-ingest.json`, `normalized/<stamp>.json`, and optionally `raw/<stamp>-<producer>.txt`.
- `ingest-to-digest` makes the next digest use ingested items and show `扫描时间范围：<min fetched_at> 至 <max fetched_at>`.
- `ingest-reject-version` rejects payloads with the wrong `interface_version`.
- `ingest-drop-invalid` drops items missing title/source/fetched_at/body or containing prompt-injection phrases.

## How to get to it (user POV)

- User confirms a runtime-retrieval source (e.g. "这次可以用 agent-reach 抓一下"); during a digest run the agent calls `retrieval-request`, fetches, then `ingest`.
- Operator runs `retrieval-request` / `ingest` commands directly.

## Driving it with verify-skrya

Preconditions:

- Fresh run launched and `$V doctor` clean.
- `agi-news` has two enabled `runtime-retrieval` sources and no ingest yet.

- **Request.** Run `$V skrya rr -- retrieval-request --root . --topic agi-news`. Exit `0`; stdout JSON has `"interface_version": "skrya.retrieval-request.v1"`, `"topic_id": "agi-news"`, capabilities `web_search`, `news_search`, five queries including `AGI benchmark`.
- **Write a payload.** Create `$($V path work)/ingest.json`:
  `{"interface_version":"skrya.ingest.v1","topic_id":"agi-news","retrieved_at":"2026-10-19T09:00:00+08:00","producer":{"kind":"runtime-skill","name":"verify-fixture","persistent":false,"capabilities":["web_search"]},"items":[{"id":"verify-agi-1","title":"验证用条目：某实验室发布新的推理评测基准","url":"https://example.com/verify-agi-1","source_name":"Example","fetched_at":"2026-10-19T08:59:00+08:00","language":"zh-CN","summary":"验证用摘要：新的推理基准公布，多家模型首次参与评测。"}]}`
- **Record.** Run `$V skrya ingest -- ingest --root . --topic agi-news --file "$($V path work)/ingest.json" --raw-file "$($V path work)/ingest.json"` then `$V snapshot after-ingest`. Stdout `Recorded ingest: <scratch>/data/runs/agi-news/ingest/latest-ingest.json`; snapshot has `ingest/latest-ingest.json`, `ingest/normalized/2026-10-19T09-00-00-08-00.json`, `ingest/raw/2026-10-19T09-00-00-08-00-verify-fixture.txt`.
- **Digest uses it.** Run `$V skrya digest -- digest --root . --topic agi-news --preview`. Exit `0`; exactly one item `【简讯1】验证用条目：某实验室发布新的推理评测基准` with `信源：[example.com](https://example.com/verify-agi-1)`, and `扫描时间范围：2026-10-19T08:59:00+08:00 至 2026-10-19T08:59:00+08:00`. Sample events do not appear.
- **Wrong version.** Write `{"interface_version":"skrya.ingest.v0"}` to `$($V path work)/bad.json` and run `$V skrya bad -- ingest --root . --topic agi-news --file "$($V path work)/bad.json"`. Exit `1`; last stderr line `ValueError: Unsupported ingest interface version: skrya.ingest.v0`.

## Gotchas

- Once `latest-ingest.json` exists, non-`--sample` digests prefer it over everything; `--sample` bypasses it.
- `producer.name` belongs only in run artifacts; never assert it appears in `sources.json`.
- Use Chinese item text for zh-CN topics, or non-Chinese titles trigger network translation.
