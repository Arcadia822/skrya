<div align="center">

# Skrya

**Turn "keep me updated on this" into a durable AI briefing workflow.**

[![Python](https://img.shields.io/badge/python-%E2%89%A53.10-3776ab.svg)](https://www.python.org)
![Skrya](https://img.shields.io/badge/skrya-v0.1.0-0ea5e9.svg)

[简体中文](README.zh-CN.md) · **English**

</div>

Skrya is a briefing skill pack for AI agents. The user describes what they want to track; the agent turns that into a durable topic with confirmed scope, confirmed sources, recurring delivery, daily digests, follow-up analysis, and long-term feedback memory.

## What You Get

```text
User: Track important AI browser developments for me every day.

Skrya turns it into:
1. topic scope: AI browsers, browser agents, search/browser distribution shifts
2. source policy: official releases, major tech media, product updates, social signals
3. recurring briefing: delivered back to the original conversation or channel
4. daily digest: uniform format, compact sources, follow-up commands
5. follow-up threads: continuing stories stay connected instead of resetting every day
```

```markdown
# 2026-05-08 | AI Browsers | Daily Briefing

### N-01 OpenAI browser rumors matter because the browser can become the agent runtime
The durable shift is identity, page state, and tool use moving into one workflow.
Sources: official blog | major tech media | product pages

### N-02 Perplexity, Arc, and adjacent products blend search, browsing, and agent actions
AI browsers change distribution for search and task execution.
Sources: product updates | media reports | user feedback

---

## Available actions

- Reply `dig: N-01` for deeper news analysis.
- Reply `track: N-02` to propose a continuing Thread.
- Reply `dig: T-01` for complete Thread history.
- Reply `write: T-01` for a sourced article draft, without publishing.
- Send natural-language feedback to adjust future briefings.
```

See more demos: [AI browser daily briefing](examples/ai-browser-daily-briefing.md), [new energy thread](examples/new-energy-thread-demo.md), and [research agent watchlist](examples/research-agent-watchlist.md).

Digest templates can be created or updated. Create drafts a new candidate from the default contract without reading an existing topic template; update reads the configured template and drafts a revision. Both use the same active-Thread contract validation and verified save gate, and failed validation neither creates nor overwrites the target.

Feishu supports native Schema 2.0 cards, explicit-target delivery, complete body threads and lossless splitting. See [native channel delivery](docs/channel-adapters.md) for commands, credential isolation and delivery receipts. Rendering is not evidence of delivery.

## Quick Start

Send this to your agent:

```text
Install Skrya from https://github.com/Arcadia822/skrya. After installation, send me a daily briefing about important AI browser developments.
```

The agent should read the repository installation instructions and handle the setup. You should not need to copy shell commands manually. After installation, it should clarify what you actually want, then confirm sources and delivery. It should not dump search results immediately. We are all grateful for this restraint.

Manual install:

```bash
git clone https://github.com/Arcadia822/skrya.git
cd skrya
python3 -m pip install -e .
./setup --host auto
```

## Core Value

### Daily Briefings

Turn a standing area of interest into a reusable daily briefing. Each item has source references, judgment, and follow-up actions.

### Source Discipline

Skrya confirms sources before declaring a topic ready. It distinguishes automatically connected sources, runtime retrieval sources, and sources that cannot be connected yet.

Direct RSS and Atom feeds and RSSHub routes are collected by Skrya itself: feed parsing and event normalization (`skrya.ingest.v2`) are part of the project, so the external search tools your agent already uses keep their interfaces unchanged. When a confirmed RSSHub source cannot be fetched directly, Skrya hands off at runtime: it asks the agent's provider-neutral web/news retrieval to cover that same confirmed source by name and route, instead of inventing article URLs or silently substituting another source. Explicit fallback capabilities and queries take precedence; older configurations without them get a runtime request based on the confirmed source name, route, and topic brief, without changing durable configuration.

Domain presets under `source-curation/presets/` (AI/LLM, technology news, developer tools, new energy vehicles, cryptocurrency) plus a curated RSSHub route directory are advisory starting points, not preconnected sources. Every preset entry still needs user confirmation and a live probe before activation. The route directory does not guarantee that any instance or route is currently reachable. Confirm RSSHub instances and routes, and agree on fallback capabilities and queries before enabling them.

### Skill Composition

Skrya looks for useful local skills and uses them to widen source coverage. For example, it can work with `agent-reach` for public web and social retrieval, or `wechat-article-search` for WeChat Official Account articles. Skrya does not focus on bypassing login walls or access restrictions; it organizes available sources into reusable briefing workflows.

### Continuing Threads

The same developing story should not become unrelated headlines every day. Skrya links related items into a continuing thread so the context stays visible.

### Feedback Becomes Memory

When you say "show fewer items like this", "keep tracking this", or "expand item 3", Skrya turns that into durable preferences instead of treating it as disposable chat.

### Digest Hygiene And Local Caches

Identical repeats of a story (same event identity and unchanged content) are hidden when they already appeared in any of the last three real digests; changed content reappears, and preview runs never change this memory. Skrya computes `event_id` from `source_id` and the exact article URL, or the normalized title when no article URL exists. It computes `content_hash` from normalized title, summary, and content without rewriting stored article URLs. Each successful non-preview source collection advances that source's generation, including successfully parsed cached responses; failures and skipped sources do not. The latest generation defines the current set, while older records and full raw Thread history remain stored in `runs/<topic-id>/event-state.json` and Thread artifacts. Ingest state written by older versions (`skrya.ingest.v1`) is converted only by the explicit `upgrade --migrate-ingest-v2` step, which backs up the current file first; see [upgrading](docs/upgrade.md).

Two persistent local caches avoid repeated network work: an HTTP cache with conditional freshness for feed collection, and a non-expiring content-hash translation cache for Chinese output. `digest --force-refresh` bypasses HTTP cache freshness for one run, and the `cache` command clears or cleans up recognized cache entries only (`--clear-http-cache`, `--clear-translation-cache [--translation-language zh-CN]`, `--cleanup-expired`); with no action flags it reports usage and clears nothing. Preview runs leave the data root byte-for-byte unchanged.

Per-source health is tracked in the topic directory: repeated failures mark a source degraded and apply temporary backoff, and `source-health --topic <topic-id>` reports it (`--refresh` runs one live collection for that topic). A concise health notice appears before the first digest section, without adding a sixth action. A live digest never silently substitutes sample events for configured sources that fail.

Archived ingest batches accumulate under `runs/<topic-id>/ingest/`. `ingest-prune --topic <topic-id> --keep 10` is a dry-run by default that reports which batches would be removed; only `--apply` deletes the selected batches, and digests, `.events.json` snapshots, threads, receipts, and bindings are never touched. The latest referenced batch is protected. Review the dry-run selection before applying it.

### Channel Isolation

In hosts with channels or conversations, a briefing created in one channel stays bound to that channel by default. Resends and empty-briefing diagnosis do not pull in another channel's topic.

## Language

Skrya does not need an install-time language setting. Language belongs to the topic:

- New topics default to the language used when the topic is created.
- You can explicitly ask for a topic to output in Chinese or English.
- The project currently supports Chinese and English output.
- If you give feedback in another language later, the agent should answer in your feedback language without changing the topic's briefing language unless you ask.

## Privacy

Skrya runs fully locally. It has no telemetry, cloud sync, or hosted backend, and it does not proactively upload your topic config, briefing history, feedback preferences, or local data. Other networked skills you ask the agent to combine with Skrya, such as web retrieval, browser tools, or WeChat article search, follow their own external-access rules.

## Uninstall

Skrya supports three uninstall modes:

| Mode | Removes | Keeps |
| --- | --- | --- |
| `skills-keep-data` | Installed skills | Topic config, history, data-root config |
| `data-keep-skills` | Skrya data and data-root config | Installed skills |
| `complete` | Skills, data, and Skrya routing notes in global instructions | Unrelated user instructions |

Tell your agent:

```text
Uninstall Skrya. First explain the three uninstall modes, then wait for my confirmation before acting.
```

Complete uninstall removes only marked Skrya instruction blocks such as `SKRYA-ROUTING-NOTE`. It should not wipe unrelated `AGENTS.md`, `CLAUDE.md`, `TOOLS.md`, or `tools.md` content.

## More Docs

| Doc | Covers |
| --- | --- |
| [Install](INSTALL.md) | Agent-facing install, uninstall, and upgrade steps |
| [User journeys](docs/user-journeys.md) | How agents should behave for nontechnical users |
| [Threads](docs/threads.md) | Continuing event timelines |
| [Delivery bindings](docs/delivery-bindings.md) | How topic delivery stays isolated to the creating channel and user context |
| [Source health](docs/source-health.md) | Per-source failure tracking, backoff, and diagnostics |
| [HTTP cache](docs/http-cache.md) | Persistent HTTP caching with conditional freshness |
| [Translation cache](docs/translation-cache.md) | Content-hash translation caching for Chinese output |
| [External retrieval](docs/external-retrieval-interface.md) | Runtime retrieval normalization |
| [Domain model](docs/domain-model.md) | Topic, request, source, thread, channel, and related entities |
| [Contributing](CONTRIBUTING.md) | Development, tests, code layout, and technical design |

## License

[MIT](LICENSE)
