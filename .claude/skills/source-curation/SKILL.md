---
name: source-curation
description: Use when the user wants to add, remove, or refine sources for a configured topic after the briefing intent is already clear.
---
# Source Curation

Curate sources for a configured topic after the topic intent is already clear.

Always require an explicit `topic-id`.

## Read First

- `topics/<topic-id>/topic.json`
- `topics/<topic-id>/brief.json`
- `topics/<topic-id>/sources.json`

If recent digest behavior matters to the source decision, also read:

- `topics/<topic-id>/digest.md`
- `runs/<topic-id>/latest-digest.md` when available

Also inherit any applicable workspace defaults from `CLAUDE.md`.

## Core Rule

先用已经确认的 topic intent 判断“什么信源更合适”，再讨论是否写入 `sources.json`。不要在意图没澄清之前直接堆来源。

## Feasibility Rule

- 有 RSS，可接入
- 没有 RSS，当前不可接入

## Required Behavior

1. Make sure the topic intent is already clear enough to judge source fit.
2. Evaluate each proposed source against that confirmed intent.
3. Explain recommendations in terms of event coverage, not generic source prestige.
4. Say clearly when a desired source is not connectable under the current RSS-only rule.
5. Confirm additions or removals before writing `sources.json`.

## Output Rules

- Keep source discussion practical and concise.
- Do not write unconfirmed source candidates into `sources.json`.
- Prefer sources that repeatedly surface the kinds of events the user actually wants.

## Success Criteria

After this skill completes:

- source recommendations are tied to confirmed topic intent
- non-RSS sources are filtered out clearly
- `sources.json` only changes after explicit confirmation
