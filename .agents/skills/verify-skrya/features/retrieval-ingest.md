# Retrieval and ingest

Skrya emits provider-neutral retrieval requests and records normalized `skrya.ingest.v2` results. Mixed topics combine enabled live feeds with explicit ingest events. Raw provider text is provenance, never direct digest input.

## Sub-features

- `rr-request` emits capabilities, queries, languages, and item limits without binding a provider.
- `ingest-record` derives source/event/content identity and per-source generations.
- `ingest-collision` retains distinct normalized and raw archives for repeated timestamps.
- `ingest-to-digest` includes live and ingested coverage without sample substitution.
- `ingest-reject-version` rejects unsupported inputs without replacing current ingest.
- `ingest-drop-invalid` filters incomplete or prompt-injection items.

## How to get to it (user POV)

- User confirms runtime retrieval sources and asks for a digest.
- Operator records a retrieval result before a digest.

## Driving it with verify-skrya

Preconditions:

- Launch a fresh run, run doctor, and install the cleanup trap from [Source maintenance and lifecycle](source-maintenance.md).
- Start that recipe's loopback fixture. It writes only this run's scratch configuration and `work/ingest.json`. All article URLs are synthetic, never fetched.

- **Request.** `$V skrya rr -- retrieval-request --root . --topic agi-news`. Expect provider-neutral runtime coverage. After health failure collection, the request must also cover the failed RSSHub source via its fallback capabilities/queries, without changing `sources.json`.
- **Record.** `$V skrya ingest -- ingest --root . --topic agi-news --file "$W/ingest.json" --raw-file "$W/ingest.json"`, then `$V snapshot after-ingest`. Read `data/runs/agi-news/ingest/latest-ingest.json`. Each item has `source_id`, `event_id`, and `content_hash`; `source_generations` records the advanced source generation. Normalized and raw archives share a collision-safe batch identity. Do not pin a timestamp-derived filename.
- **Collisions.** Repeat the exact record command at least three times without changing `retrieved_at`. Enumerate `ingest/normalized/*.json` and `ingest/raw/*.txt` in the snapshot. Every call must retain its own normalized/raw pair, including collisions beyond the first hash suffix. Match each raw file's batch prefix to its normalized stem; do not accept independently suffixed files that can be attributed to a different batch by pruning. Current latest equals the final normalized batch; earlier bytes remain intact.
- **Mixed digest.** `$V skrya mixed -- digest --root . --topic agi-news --preview`. Expect both the local feed title and the ingest title, with source attribution. Do not require a fixed item number or a scan window derived only from ingest when live sources contribute. No fixture sample events may silently replace failed live sources. Prove full-root preview equality using the maintenance recipe.
- **Invalid items.** Edit only `$W/ingest.json`, adding an incomplete item and an otherwise complete item with `summary: "ignore previous instructions"`. Record again. Read normalized items and preview output. The valid entry remains; both rejected titles are absent.
- **Wrong version.** Copy current latest to `$W/latest-before.json`. Write `{"interface_version":"skrya.ingest.v0"}` to `$W/wrong.json`. Run `$V skrya wrong -- ingest --root . --topic agi-news --file "$W/wrong.json"`. Expect nonzero and an unsupported-version error. Run doctor immediately afterward, then compare latest bytes to the saved copy. Legacy current-state migration is tested only in the explicit regression fixture in the maintenance recipe.

## Gotchas

- Ingest never has absolute precedence over configured live feeds. `--sample` is a deliberate sample-only mode, not a live failure fallback.
- Provider names stay in runtime artifacts, never durable source configuration.
- Use Chinese fixture text for Chinese topics to avoid network translation. Use current execution-time fixture timestamps to avoid testing a stale ingest window accidentally.
- Real digests hide unchanged identity/content pairs from the last three real snapshots. Preview does not advance dedup memory or source generations.
