---
name: source-curation
description: Use when the user wants to add, remove, or refine sources, auto-connectable channels, or runtime retrieval capabilities for a configured topic after the briefing intent is already clear. Trigger for Chinese requests like "用某个检索工具抓一下", "把这个来源加进去", "这个网站能不能接入", or "换一批来源".
---
<!-- AUTO-GENERATED from source-curation/SKILL.md.tmpl; regenerate with `python -m skrya_orchestrator.main build-skill-pack --root . --host all` -->

# Source Curation

Curate sources for a configured topic after the topic intent is already clear.

Always resolve an explicit internal `topic-id` before reading or writing files, but do not ask nontechnical users for raw ids when a natural topic name can be mapped.

## Read First

- `topics/<topic-id>/topic.json`
- `topics/<topic-id>/brief.json`
- `topics/<topic-id>/sources.json`

If recent digest behavior matters to the source decision, also read:

- `topics/<topic-id>/digest.md`
- `runs/<topic-id>/latest-digest.md` when available

Also inherit any applicable workspace defaults from `AGENTS.md`, `CLAUDE.md`, or the equivalent repository instruction file.

## Core Rule

Use confirmed topic intent to judge which sources are a fit before changing `sources.json`.

## Feasibility Rule

- internally, sources with RSS are connectable
- internally, sources without RSS are not connectable for now
- Do not expose RSS as a user-facing requirement.
- Tell the user whether a source can be "自动接入" or is "暂时不能自动接入" under the current connector limits.
- When the channel depends on a runtime retrieval skill, write a provider-neutral `runtime-retrieval` source that records capabilities, queries, languages, and time windows.
- If the user mentions a specific provider such as `agent-reach`, do not save the provider name in durable `sources.json`; keep it only in runtime ingest artifacts.

## Required Behavior

1. Make sure the topic intent is already clear enough to judge source fit.
2. Evaluate each proposed source against that confirmed intent.
3. Explain recommendations in terms of event coverage, not generic source prestige.
4. Say clearly when a desired source is not currently auto-connectable, without making the user reason about RSS.
5. Confirm additions or removals before writing `sources.json`.
6. For runtime retrieval channels, write capabilities such as `web_search`, `news_search`, `site_search`, `social_search`, or `document_fetch`, not third-party skill names.

## Output Rules

- Keep source discussion practical and concise.
- Do not write unconfirmed source candidates into `sources.json`.
- File names are internal execution details; do not show file names in normal user-facing replies unless the user asks for implementation details.
- Prefer sources that repeatedly surface the kinds of events the user actually wants.

## Success Criteria

After this skill completes:

- source recommendations are tied to confirmed topic intent
- sources that cannot be auto-connected are filtered out or explained clearly
- `sources.json` only changes after explicit confirmation
