# Daily digest

A user asks for today's briefing or a scheduled automation runs it. Skrya writes a readable Markdown digest with N-xx news, active T-xx Threads first, sources, and exactly five follow-up actions under `## 可继续操作` (English: `## Available actions`). Formal runs freeze a timestamped Markdown artifact and matching `.events.json`; previews write nothing. Native Feishu presentation is a separate rendering step.

## Sub-features

- `digest-real` writes a timestamped digest, its immutable `.events.json` sidecar, `latest-digest.md`, and the latest-only compatibility index `latest-digest-events.json`.
- `digest-latest-pointer` repoints `latest-digest.md` to the newest artifact on each run.
- `digest-preview` (`--preview` / `--test-run`) renders identically but writes nothing.
- `digest-thread-section` shows every active thread, with either a verified increment or an explicit "本轮暂无可核验新增" review state.
- `digest-empty` refuses to pass sample data off as real when live sources produced nothing.
- `digest-topic-by-name` accepts the topic's display name instead of its id.
- `digest-unknown-topic` fails clearly for a topic that does not exist.

## How to get to it (user POV)

- User says "给我今日简报" / "跑一次日报" / asks for a test run in an agent with Skrya installed; the `digest` skill calls `digest --topic <id>` (or `--preview` for a test run).
- Scheduled automation prompt runs the same `digest` command.
- Operator runs `python3 -m skrya_orchestrator.main digest --root . --topic <id>` directly.

## Driving it with verify-skrya

Preconditions:

- Fresh run launched and `$V doctor` clean.
- No `runs/new-energy-vehicles/` yet.

- **Preview writes nothing.** Run `$V skrya preview -- digest --root . --topic new-energy-vehicles --sample --preview` then `$V snapshot after-preview`. Exit `0`; stdout starts with `# <YYYY-MM-DD>｜新能源汽车｜每日简报`; the snapshot contains `runs-absent.txt` (no `runs/` created).
- **Real digest.** Run `$V skrya digest -- digest --root . --topic new-energy-vehicles --sample`. Exit `0`; active `### T-01 比亚迪闪充站` precedes news `### N-01` through `### N-03`, each with sources. The footer contains news dig/track, Thread dig/write, and natural-language feedback; no old line boxes or runtime metadata.
- **Artifacts written.** Run `$V snapshot after-digest`. The timestamped Markdown equals `stdout.txt`. Its same-stem `.events.json` has schema `skrya.digest-index.v1`, original artifact SHA256, `items` keyed by N-xx and `threads` keyed by T-xx. `latest-digest.md` points to it; the separate latest compatibility index still has `items[]`. Thread raw history remains under `threads/latest-threads.json`.
- **Pointer moves without rewriting old snapshots.** Run `$V skrya digest-again -- digest --root . --topic 新能源汽车 --sample` and snapshot again. A new Markdown/sidecar pair exists, latest points to it, and the first pair's bytes are unchanged. No sleep is required: same-second runs receive unique suffixes.
- **Thread with no increment.** Run `$V skrya live-empty -- digest --root . --topic new-energy-vehicles --preview` (no `--sample`, no ingest). The active T-01 remains with an explicit no-verified-update message, latest state and next observation; no sample news is passed off as current.
- **Empty topic without threads.** Run `$V skrya agi-empty -- digest --root . --topic agi-news --preview`. Stdout has the title, the same "暂时没有抓到足够新的真实内容" line, and no `## 事件线时间线更新`.
- **Unknown topic.** Run `$V skrya unknown -- digest --root . --topic nope --preview`. Exit `1`; stderr is `Digest failed: Topic 'nope' not found`.

## Gotchas

- Timestamp collisions allocate a suffix instead of overwriting existing Markdown or snapshots.
- Without `--sample`, `k-entertainment` fetches live RSS feeds; use `--sample` for deterministic proof and report the fixture boundary.
- The digest footer no longer contains version, Agent or LLM execution metadata.
- Preview does not refresh `latest-digest-events.json`; the legacy numeric analysis command still uses the last real digest. Current agent follow-ups instead use their explicit artifact or received-message snapshot.
